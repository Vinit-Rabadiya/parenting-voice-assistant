# Troubleshooting

[Documentation home](../README.md#documentation).

| Symptom | Check |
|---|---|
| Authentication temporarily unavailable | Backend internet access to Firebase; a healthy liveness endpoint does not verify cloud connectivity |
| Child profiles fail to load | Firestore API activation, default database creation, service-account permissions, and backend logs |
| Guidance generation fails | Qdrant and selected provider configuration, model access, quotas, and backend diagnostic messages |
| Coaching service temporarily busy (503) | The selected provider reported service unavailability. Retry later; the application does not add automatic retries. |
| Coaching service request limit reached (429), single-provider mode | Check the selected provider's quota and usage. Cross-provider mode automatically tries the other eligible service instead. |
| Guidance could not be provided (`safety_blocked`) | The model service blocked a response or an answer matched an output guardrail. Only a clear replacement message is returned and stored, without supporting source cards. |
| Frontend reports connection refused | Backend is ready on port 8000 and both development servers are running |
| Microphone is unavailable | Site permission, supported browser, and localhost or HTTPS |
| Port 8000 is occupied | Stop the earlier backend process before starting another instance |
