#!/usr/bin/env bash

readonly NOTIFICATION_NAMESPACE=atlas-extended-notifications
readonly NOTIFICATION_RECEIVER=notification-receiver

notification_wait_events() {
  local path=$1 minimum=$2 timeout_seconds=${3:-180} elapsed=0 count=0
  while (( elapsed < timeout_seconds )); do
    count=$(k -n "$NOTIFICATION_NAMESPACE" logs "deployment/${NOTIFICATION_RECEIVER}" 2>/dev/null | grep -Fc "\"path\":\"${path}\"" || true)
    (( count >= minimum )) && return 0
    sleep 2
    elapsed=$((elapsed + 2))
  done
  die "Notification receiver eventが不足しています: path=${path} actual=${count} expected>=${minimum}"
}

notification_patch_config() {
  local failure_url=$1 patch normal_service failure_service
  printf -v normal_service 'url: http://%s.%s.svc.cluster.local\nheaders:\n- name: Content-Type\n  value: application/json\nretryWaitMin: 1000000000\nretryWaitMax: 1000000000\nretryMax: 2' "$NOTIFICATION_RECEIVER" "$NOTIFICATION_NAMESPACE"
  printf -v failure_service 'url: %s\nheaders:\n- name: Content-Type\n  value: application/json\nretryWaitMin: 1000000000\nretryWaitMax: 1000000000\nretryMax: 2' "$failure_url"
  patch=$(jq -n \
    --arg normal_service "$normal_service" \
    --arg failure_service "$failure_service" \
    --arg normal_template $'webhook:\n  atlas-normal:\n    method: POST\n    path: /normal\n    body: |\n      {"application":"{{.app.metadata.name}}","sync":"{{.app.status.sync.status}}","health":"{{.app.status.health.status}}","revision":"{{.app.status.sync.revision}}"}' \
    --arg failure_template $'webhook:\n  atlas-failure:\n    method: POST\n    body: |\n      {"application":"{{.app.metadata.name}}","phase":"{{.app.status.operationState.phase}}","case":"failure-recovery"}' \
    --arg normal_trigger $'- when: app.status.operationState.phase in [\'Succeeded\'] and app.status.health.status == \'Healthy\'\n  oncePer: app.status.sync.revision\n  send: [atlas-normal]' \
    --arg failure_trigger $'- when: app.status.operationState.phase in [\'Succeeded\'] and app.status.health.status == \'Healthy\'\n  send: [atlas-failure]' \
    '{data:{"service.webhook.atlas-normal":$normal_service,"service.webhook.atlas-failure":$failure_service,"template.atlas-normal":$normal_template,"template.atlas-failure":$failure_template,"trigger.atlas-normal":$normal_trigger,"trigger.atlas-failure":$failure_trigger}}')
  k -n "$ARGOCD_NAMESPACE" patch configmap argocd-notifications-cm --type merge -p "$patch" >/dev/null
}

notification_capture_metrics() {
  local output=$1 port_forward_log="${EXTENDED_RUNTIME}/notifications-port-forward.log" pid elapsed=0
  k -n "$ARGOCD_NAMESPACE" port-forward service/argocd-notifications-controller-metrics 19091:9001 >"$port_forward_log" 2>&1 &
  pid=$!
  while (( elapsed < 30 )); do
    if curl --fail --silent --show-error http://127.0.0.1:19091/metrics -o "$output"; then
      kill "$pid" >/dev/null 2>&1 || true
      wait "$pid" 2>/dev/null || true
      return 0
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done
  kill "$pid" >/dev/null 2>&1 || true
  wait "$pid" 2>/dev/null || true
  die 'Notification controller metricを取得できません'
}

phase_setup() {
  extended_init notifications
  local backup_dir name
  backup_dir="${EXTENDED_RUNTIME}/backup/notifications"
  name=$(extended_name notifications)
  mkdir -p "$backup_dir"
  k -n "$ARGOCD_NAMESPACE" get configmap argocd-notifications-cm -o json >"${backup_dir}/argocd-notifications-cm.json"
  extended_apply_project_app notifications apps/application
  cat <<EOF | k apply -f - >/dev/null
apiVersion: v1
kind: ConfigMap
metadata:
  name: notification-receiver-script
  namespace: ${NOTIFICATION_NAMESPACE}
data:
  receiver.py: |
    import json
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                body = {"invalid_json": True}
            status = 503 if self.path == "/fail" else 200
            print("ATLAS_RECEIVER " + json.dumps({"path": self.path, "status": status, "body": body}, separators=(",", ":")), flush=True)
            self.send_response(status)
            self.end_headers()
            self.wfile.write(b"ok" if status == 200 else b"retry")
        def log_message(self, format, *args):
            return
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ${NOTIFICATION_RECEIVER}
  namespace: ${NOTIFICATION_NAMESPACE}
spec:
  replicas: 1
  selector:
    matchLabels: {app: ${NOTIFICATION_RECEIVER}}
  template:
    metadata:
      labels: {app: ${NOTIFICATION_RECEIVER}}
    spec:
      automountServiceAccountToken: false
      containers:
        - name: receiver
          image: ${SUPPORT_IMAGE}
          command: [python, /srv/receiver.py]
          ports: [{containerPort: 8080}]
          readinessProbe:
            tcpSocket: {port: 8080}
            periodSeconds: 2
          volumeMounts:
            - {name: script, mountPath: /srv, readOnly: true}
      volumes:
        - name: script
          configMap: {name: notification-receiver-script}
---
apiVersion: v1
kind: Service
metadata:
  name: ${NOTIFICATION_RECEIVER}
  namespace: ${NOTIFICATION_NAMESPACE}
spec:
  selector: {app: ${NOTIFICATION_RECEIVER}}
  ports: [{port: 80, targetPort: 8080}]
EOF
  k -n "$NOTIFICATION_NAMESPACE" rollout status "deployment/${NOTIFICATION_RECEIVER}" --timeout=180s
  notification_patch_config "http://${NOTIFICATION_RECEIVER}.${NOTIFICATION_NAMESPACE}.svc.cluster.local/fail"
  sleep 3
  k -n "$ARGOCD_NAMESPACE" annotate application "$name" \
    notifications.argoproj.io/subscribe.atlas-normal.atlas-normal='' --overwrite >/dev/null
  notification_wait_events /normal 1 180
}

phase_execute() {
  local name
  name=$(extended_name notifications)
  k -n "$ARGOCD_NAMESPACE" annotate application "$name" \
    notifications.argoproj.io/subscribe.atlas-failure.atlas-failure='' --overwrite >/dev/null
  notification_wait_events /fail 3 180
  notification_patch_config "http://${NOTIFICATION_RECEIVER}.${NOTIFICATION_NAMESPACE}.svc.cluster.local/recovered"
  sleep 3
  k -n "$ARGOCD_NAMESPACE" annotate application "$name" \
    atlas.openai.com/notification-retry="$(date -u '+%Y-%m-%dT%H:%M:%SZ')" --overwrite >/dev/null
  notification_wait_events /recovered 1 180
}

phase_verify() {
  local receiver_log metrics_file controller_log events normal_count failure_count recovered_count app_name
  app_name=$(extended_name notifications)
  receiver_log="${EXTENDED_RUNTIME}/traces/notifications-receiver.log"
  metrics_file="${EXTENDED_RUNTIME}/traces/notifications-metrics.prom"
  controller_log="${EXTENDED_RUNTIME}/traces/notifications-controller.log"
  k -n "$NOTIFICATION_NAMESPACE" logs "deployment/${NOTIFICATION_RECEIVER}" >"$receiver_log"
  k -n "$ARGOCD_NAMESPACE" logs deployment/argocd-notifications-controller --since=20m >"$controller_log"
  notification_capture_metrics "$metrics_file"
  events=$(sed -n 's/^ATLAS_RECEIVER //p' "$receiver_log" | jq -s '.')
  normal_count=$(jq '[.[]|select(.path=="/normal" and .status==200 and .body.application==$app and .body.sync=="Synced" and .body.health=="Healthy")]|length' --arg app "$app_name" <<<"$events")
  failure_count=$(jq '[.[]|select(.path=="/fail" and .status==503 and .body.application==$app)]|length' --arg app "$app_name" <<<"$events")
  recovered_count=$(jq '[.[]|select(.path=="/recovered" and .status==200 and .body.application==$app)]|length' --arg app "$app_name" <<<"$events")
  (( normal_count >= 1 )) || die '正常Notification deliveryがありません'
  (( failure_count >= 3 )) || die "HTTP 5xx retry attemptが不足しています: ${failure_count}"
  (( recovered_count >= 1 )) || die 'Endpoint回復後のNotification deliveryがありません'
  grep -Fq 'argocd_notifications_deliveries_total' "$metrics_file" || die 'Notification delivery metricがありません'
  grep -Fq 'argocd_notifications_trigger_eval_total' "$metrics_file" || die 'Notification trigger metricがありません'
  jq -n \
    --arg application "$app_name" \
    --argjson receiver_events "$events" \
    --argjson normal_count "$normal_count" \
    --argjson failure_count "$failure_count" \
    --argjson recovered_count "$recovered_count" \
    --arg controller_log_digest "sha256:$(sha256_file "$controller_log")" \
    --arg metrics_digest "sha256:$(sha256_file "$metrics_file")" \
    --argjson delivery_metrics "$(grep -E '^argocd_notifications_(deliveries|trigger_eval)_total' "$metrics_file" | jq -R -s 'split("\n")|map(select(length>0))')" \
    '{notifications:{application:$application,subscription_scope:"application-annotation",receiver:"in-cluster-local-http",receiver_events:$receiver_events,normal_delivery_count:$normal_count,http_503_attempt_count:$failure_count,recovered_delivery_count:$recovered_count,retry_max:2,controller_log_digest:$controller_log_digest,metrics_digest:$metrics_digest,metric_samples:$delivery_metrics,secret_values_captured:false,external_delivery:false,assertions:{normal_delivery:true,http_5xx_retried:true,endpoint_recovery_delivery:true,controller_metrics_present:true},non_guarantees:["global subscription","provider-specific authentication","rate limit behavior","deduplication across controller restart","all notification services"]}}' \
    >"$(extended_trace_file notifications)"
  extended_capture notifications
}

phase_cleanup() {
  local backup_dir original_data
  backup_dir="${EXTENDED_RUNTIME}/backup/notifications"
  extended_cleanup_project_app notifications
  if [[ -s "${backup_dir}/argocd-notifications-cm.json" ]]; then
    original_data=$(jq -c '.data // {}' "${backup_dir}/argocd-notifications-cm.json")
    k -n "$ARGOCD_NAMESPACE" patch configmap argocd-notifications-cm --type json \
      -p "[{\"op\":\"replace\",\"path\":\"/data\",\"value\":${original_data}}]" >/dev/null
  fi
  rm -f -- "${backup_dir}/argocd-notifications-cm.json"
  rmdir "$backup_dir" 2>/dev/null || true
}
