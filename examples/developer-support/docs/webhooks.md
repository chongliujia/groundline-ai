# Webhook Delivery Runbook

Groundline Cloud sends webhook events to developer-owned HTTPS endpoints.

## Delivery Requirements

Webhook endpoints must respond with a 2xx status within ten seconds. The
platform retries failed deliveries with exponential backoff. A delivery is
considered failed when the endpoint times out, returns a non-2xx status, or
terminates the TLS handshake.

## Triage Checklist

Before escalating a webhook delivery issue, support should check:

1. The endpoint URL uses HTTPS and has a valid certificate.
2. Recent deliveries show consistent request ids and event ids.
3. The customer endpoint returned a 2xx status for at least one retry.
4. The signing secret configured in the developer console matches the receiving
   service.
5. The customer's firewall allows inbound requests from the documented egress
   ranges.

Escalate only after collecting the event id, request id, delivery timestamp,
endpoint URL, response status, and retry count.

## Signing

Every webhook includes a signature header. Receivers should verify the signature
before processing the payload and reject stale timestamps.

