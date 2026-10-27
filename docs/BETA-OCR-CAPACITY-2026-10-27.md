# OCR capacity and recovery

The existing Render service remains on `0.5c-512mb`. No compute-plan or billing change was made in this pass.

A small synthetic PNG caused an actual beta restart. Render event `evt-dbg2dfdg1s2s7389ommg` at 2026-10-27 04:21:17 UTC identifies the cause as `oomKilled`, memory limit `512Mi`. Native PDF, DOCX, CSV and XLSX uploads had already processed successfully. The failed OCR test document was removed through the supported ingestion API; existing documents were not removed.

| Isolated full-app allocation | Work | Observed result |
|---|---|---|
| 512 MiB, 0.5 CPU, no swap | Small PNG OCR with native threads capped at one | FAIL: extractor killed, cgroup peak 536,870,912 bytes; `oom=1`, `oom_kill=1` |
| 2 GiB, 0.5 CPU, no swap | Small PNG and maximum-supported 12-megapixel PNG | OCR passed; a subsequent scanned-PDF health probe timed out. This allocation is not the recommended target. |
| 2 GiB, 1 CPU, no swap | Small PNG, 12-megapixel PNG, scanned PDF; full app running and health probed during extraction | PASS: all three recognized the synthetic text; no OOM events. Highest aggregate cgroup peak 1,355,816,960 bytes (about 1.26 GiB). Longest health response 0.401 seconds. Extraction times 19.21, 9.61 and 4.05 seconds respectively. |

These are container measurements, including the app and measurement process. They are not a 2 GB WSL acceptance test or a load-test certification. WSL was not restarted or reconfigured. Original services were left running. OCR weights and extraction resolution were not reduced.

The proposed paid target is Render `1c-2g`: $25/month compute plus the existing 1 GB disk at $0.25/month, before other workspace/usage charges. [Current Render pricing](https://render.com/pricing) and [compute-plan identifiers](https://render.com/docs/compute-plans) were checked. The earlier approved core allocation was about $7.25/month; increasing that ongoing cost requires the owner's decision. The disk-backed service must remain a single instance.

The software now refuses local OCR below a 2 GiB application budget before loading its native model. It retains the original upload and explains the required capacity or separate-worker configuration. Ordinary text-based PDF, DOCX, CSV, XLSX and text processing remain available. Parser processes use bounded native threading and receive no unrelated service credentials. Once approved capacity is present, retrying the retained upload can use the same OCR implementation.

The restart exposed a separate recovery defect: the durable external-job hold returned before recovering internal ingestion. Recovery and automatic local retries are now separate from external source polling. Interrupted managed ingestion can resume idempotently while imported external automation stays paused; repeated interruptions are bounded. Tests assert that the hold remains set and external jobs are not released.

`lab/beta_ocr_capacity.py` reproduces the synthetic measurements only inside a disposable full-app container with a synthetic capacity-test key. Use a private env file with the normal origin/CORS/bootstrap requirements, a new Docker data volume, no network, `--memory 2g --memory-swap 2g --cpus 1`. Do not point this helper at the original installation or run heavy OCR on the 512 MB beta. `lab/beta_completion_documents.py` separately checks actual deployed parsing, review, search and download; a capacity refusal is reported as BLOCKED, never as OCR success.
