# API Authentication

Groundline Cloud accepts API keys through the `Authorization` header. Developers
should send requests with `Authorization: Bearer <api_key>`.

## Key Rotation

If an API key is leaked, rotate it immediately:

1. Create a replacement key in the developer console.
2. Deploy the replacement key to the affected service.
3. Confirm that new requests succeed with the replacement key.
4. Revoke the leaked key.
5. Review recent request logs for unexpected access.

Never place API keys in source control, issue trackers, screenshots, or shared
chat logs. Store production keys in a secret manager and reference them through
environment variables.

## Support Notes

When a developer reports authentication failures, ask for the request id,
timestamp, endpoint, and response status. Do not ask the developer to paste the
full API key.

