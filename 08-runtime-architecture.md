<!-- Doc 08 — Runtime & Arsitektur (§38–56)
     Bagian dari societas-full-product-spec. Urutan dokumen diatur di README.md.
     Nomor section dipertahankan; referensi silang antar-doc memakai nomor section (#N, 5A.x, 72A.x). -->

# 38. Suggested Architecture

```text
                    +------------------+
                    |       UI         |
                    |    Web Dashboard |
                    +---------+--------+
                              |
                              v
                    +------------------+
                    |   Intake Layer   |
                    |  (Flash tier +   |
                    |   PROJECT_MAP.md)|
                    +---------+--------+
                              |
                    +---------v--------+
                    | Jev AI Router    |
                    | (Choice/Score)   |
                    +---------+--------+
                              |
                              v
                    +------------------+
                    |    Orchestrator  |
                    +---------+--------+
                              |
          +-------------------+-------------------+
          |                   |                   |
          v                   v                   v
      Agent Runtime      Task Engine        Memory Engine
          |                   |                   |
          +-------------------+-------------------+
                              |
                        Event Bus
                              |
                    +---------+---------+
                    |                   |
                    v                   v
             In-Process Channel     Local IPC
             (goroutine + channel)
                    |
             +------+------+
             |             |
          Agent A       Agent B
```

---

# 39. Internal Modules

Recommended project structure:

```text
societas/
├── internal/
│   ├── agent/
│   ├── orchestrator/
│   ├── task/
│   ├── eventbus/
│   ├── memory/
│   ├── tool/
│   ├── permission/
│   ├── approval/
│   ├── artifact/
│   └── storage/
├── api/
├── web/
├── cmd/
│   └── societas/
├── docs/
└── migrations/
```

---

# 40. Agent Runtime

Agent runtime beroperasi sebagai **Step Function**, bukan loop blocking: setiap langkah dieksekusi sebagai unit kerja yang melepas worker begitu menunggu sesuatu (model call selesai, tool selesai, approval).

```text
Receive task
    |
    v
Load context
    |
    v
Load memory
    |
    v
Call model
    |
    +---- tool call
    |       |
    |       v
    |   Tool Runtime
    |
    v
Produce message/artifact
    |
    v
Emit event
```

## 40.1 Task Parking (Step Function)

Dilarang ada blocking goroutine pada channel (mis. `<-approvalCh`) saat menunggu Human Approval.

- Saat task butuh approval, task menyimpan state terkini ke SQLite (`status: awaiting_approval`), melepas alokasi CPU/goroutine, dan me-return worker ke pool — aman saat restart/crash.
- Saat human klik Approve di dashboard, Go runtime mengeksekusi **Compare-And-Swap (CAS)** di SQLite (`status: ready`) dan menjadwalkan ulang task ke worker pool.
- Model yang sama berlaku untuk parkir lain (`paused`, `interrupted`) — worker tidak pernah idle-menunggu.

Pause kooperatif memakai `task.paused` dengan fase requested/completed (72A.8/72A.12). Task menyimpan `pause_deadline` absolut; startup mengubah `running` **dan `pausing`** menjadi `interrupted` lewat event `task.interrupted` tanpa menghilangkan deadline. Recovery/resume tetap memakai CAS. Call tool yang mungkin sudah berjalan tidak boleh diulang otomatis kecuali aman menurut I16; cancel/TTL tidak menghapus kewajiban accounting (72A.6).

## 40.2 Bound Hash Protection

Request approval mengikat `ApprovalSnapshot` berversi: `bound_hash = "sha256:" + hex_lower(SHA256(JCS(snapshot)))`, RFC 8785 (72A.8/I17), **bukan commit SHA Git mentah**. Snapshot disimpan sebagai artifact immutable dengan ID/versi/checksum tepat; grant menggemakan ID/hash, dan ID tidak pernah di-rebind. Envelope workspace/run/task/action harus cocok snapshot.

Runtime mengecek ulang binding pada grant, resume, dan tepat sebelum dispatch: input aktual, expiry, policy/contract, dan evidence. Perubahan → `approval.invalidated`, request baru memakai ID baru. Refresh task `awaiting_approval -> ready` bukan izin mutasi. Scope once/task/run tidak membebaskan pemeriksaan hash; predicate reuse/once-consumption masih keputusan terpisah.

Untuk merge, snapshot mengikat base, commit/tree kandidat final, recipe gate, dan artifact versi gate/review. Urutan wajib: rebase/resolve → freeze kandidat → gate → review → approval → final recheck + expected-base CAS (#60.4, 72A.10). Jangan membuat commit baru sesudah approval. Lock serial hanya di final check/update, tidak dipegang saat menunggu human. Git-ref CAS tidak menjamin transaksi Git+SQLite; intent/receipt recovery (W06) dan shared metadata isolation (W14) masih perlu keputusan.

---

# 41. Orchestrator

Orchestrator bertugas:

- membuat task
- routing
- delegation
- scheduling
- dependency resolution
- retry
- timeout
- escalation
- approval
- aggregation

Catatan:

- Detail routing, scheduling, stop condition, dan fan-out ada di **Section 5A.1, 5A.14, 5A.17, dan 5A.18**.
- Hanya Orchestrator yang membuat dan meng-assign task. Agent hanya mengirim `task.delegate_requested` (72A.1, I2).
- Alur pemeriksaan delegasi (fan-out, depth, dependency, policy, budget) ada di **Section 72A.10**.

---

# 42. Event Bus

Event Bus adalah backbone.

Requirements:

- asynchronous
- ordered per stream
- correlation ID
- replay support
- bounded buffers
- backpressure
- transactional outbox (wajib, lihat bawah)
- mailbox per subscriber

## 42.1 Transactional Outbox

**SQLite Event Store adalah Single Source of Truth.** Event wajib di-commit ke SQLite terlebih dahulu (transactional), baru disalurkan ke Go channel/Event Bus. Tidak ada event yang hanya hidup di memory — jika proses mati setelah commit, event tetap bisa di-replay; jika commit gagal, event dianggap tidak pernah ada.

```text
event -> COMMIT ke event store (SQLite)
            |
            v
      dispatcher -> Go channel -> subscriber
```

## 42.2 Mailbox per Subscriber

Setiap subscriber memiliki mailbox terpisah, dipisahkan antara:

- **Receiver goroutine** — inbox queue cepat, hanya mengambil event dari bus ke mailbox subscriber; tidak boleh blocking.
- **Worker goroutine** — mengeksekusi pekerjaan berat (LLM call, tool call) dari antrian mailbox.

Pemisahan ini mencegah satu agent yang lambat mem-block delivery event ke agent lain.

---

# 43. Correlation

Setiap interaction harus bisa ditelusuri.

Hierarchy:

```text
workspace
  |
  +-- run
       |
       +-- task
            |
            +-- message
                 |
                 +-- tool call
                 |
                 +-- artifact
```

Gunakan:

```text
workspace_id
run_id
task_id
message_id
correlation_id
parent_id
```

---

# 44. Retry & Failure Handling

Agent dapat gagal.

Kategori:

```text
MODEL_ERROR
TOOL_ERROR
NETWORK_ERROR
TIMEOUT
PERMISSION_DENIED
INVALID_OUTPUT
DEPENDENCY_FAILED
```

Retry policy harus configurable.

Tidak semua error boleh retry.

Contoh:

```text
Network error
 -> tool: outcome_unknown kecuali terbukti belum dispatch; periksa I16 sebelum retry

Permission denied
 -> do not retry

Invalid tool input
 -> agent correction

Model timeout
 -> bounded retry dengan guard/accounting; bukan asumsi call tanpa biaya
```

Kategori di atas dipetakan ke kode error konkret di **Section 72A.9 (Error Catalog)**, termasuk status `retryable` dan aksi default. Semua retry dihitung dalam retry budget (5A.13).

`error.retryable: true` tidak mengalahkan keamanan efek: timeout tool non-idempotent tanpa deduplikasi provider wajib rekonsiliasi atau keputusan human. Outcome kanonik `not_started`/`outcome_unknown` ada di 72A.8; gagal logis yang hasilnya diketahui memakai `tool.call_completed` `status: error`.

---

# 45. Parallelism

Agent dapat menjalankan task paralel.

Contoh:

```text
CEO
 |
 +---- Research
 |
 +---- CTO
 |
 +---- Security
 |
 +---- CPO
```

Setelah semua selesai:

```text
          Research
              \
               \
CTO ------------> CEO
               /
Security -------/
             /
           CPO
```

Orchestrator harus mengontrol concurrency.

Eksekusi boleh paralel, tapi **merge ke `main` diserialkan**: rebase/resolve → freeze kandidat final → gate → review → approval → final recheck + expected-base CAS (I17, 72A.10, **60.4 Serial Merge Queue**). Conflict dikembalikan ke Engineer; perubahan base/kandidat membatalkan evidence dan approval lama.

---

# 46. Priority

Task memiliki priority:

```text
critical
high
normal
low
background
```

Event dapat memiliki priority.

Contoh:

```text
approval.request > debug.log
```

---

# 47. Scheduling

Task dapat dijalankan berdasarkan:

- dependency
- priority
- agent availability
- resource availability
- approval status

---

# 48. Multi-Agent Conflict Resolution

Agent bisa berbeda pendapat. Mediasi organik pasif antar-agen tidak diasumsikan — perdebatan diikat oleh batas sanggahan deterministik.

## 48.1 Max 2 Rebuttals

Batas sanggahan ketat (Max 2 Rebuttals):

```text
Putaran 1: Reviewer menolak        -> Engineer memberi sanggahan/klarifikasi
Putaran 2: Reviewer menolak ulang  -> Engineer memberi sanggahan terakhir
```

Setelah putaran kedua tanpa kesepakatan, **Orchestrator memutus perdebatan secara otomatis**: task dibekukan (`blocked`) dan masalah dieskalasi ke **`escalation_lead`** — agen pengambil keputusan yang ditentukan konfigurasi `workspace.yaml` (#30.1, #36; contoh umum: CTO dengan model reasoning tier tinggi). Jika `escalation_lead: "human"`, putusan diserahkan ke pengguna via dashboard.

## 48.2 Escalation Lead Technical Verdict

`escalation_lead` menerbitkan putusan teknis mutlak sebagai artifact `decision.md`. Putusan ini mengikat dan tidak boleh didebat balik oleh agen lain. Human tetap dapat override.

## 48.3 Evidence Handoff

Orchestrator meneruskan transkrip 4 pesan debat (reject -> rebuttal -> reject -> rebuttal) secara langsung ke `escalation_lead`. Jika transkrip sangat panjang, model murah boleh merangkumnya terlebih dahulu. Handoff ini **tidak melibatkan Vector DB**.

## 48.4 Authority Clause

Template prompt agen bawahan wajib memuat klausul otoritas:

```text
Putusan {{ .EscalationLead }} yang diterbitkan dalam `decision.md` bersifat final dan mengikat.
Agen dilarang membuka kembali atau memperdebatkan putusan tersebut; wajib langsung mengeksekusi instruksi.
```

---

# 49. Human Interaction Modes

User dapat berbicara ke:

### Direct Agent

```text
@cto explain architecture
```

### CEO

```text
@ceo plan this feature
```

### Workspace

```text
@all
status update
```

### Task

```text
#TASK-102
show progress
```

---

# 50. Event Addressing

Contoh:

```text
@ceo
@cto
@research
@engineer
@all

#TASK-001
#RUN-100
```

---

# 51. Voice Mode

Future feature.

Flow:

```text
Mic
 ↓
ASR
 ↓
Agent
 ↓
LLM
 ↓
TTS
 ↓
Speaker
```

Event Bus digunakan sebagai real-time transport untuk:

- ASR chunks
- LLM token stream
- TTS audio
- interruption events
- agent events

User dapat berbicara langsung ke CEO.

Contoh:

```text
User:
"CEO, apa status project?"

CEO:
"Research sudah selesai..."
```

---

# 52. Live Multimodal Agent

Agent dapat menerima:

- text
- image
- audio
- video
- files
- structured events

Dan mengeluarkan:

- text
- audio
- image
- tool calls
- artifacts
- events

---

# 53. Event Channel Taxonomy

Channel Event Bus dapat disusun berdasarkan:

```text
workspace
agent
task
media
event
```

Contoh:

```text
workspace/tunly/events
workspace/tunly/agent/ceo
workspace/tunly/agent/cto
workspace/tunly/agent/research
workspace/tunly/task/TASK-101
workspace/tunly/voice/ceo
```

Tidak semua event harus menjadi channel permanen.

---

# 54. Streaming Priority

Event Bus dapat membantu memprioritaskan data tertentu.

Prioritas contoh:

```text
P0 = control / approval
P1 = agent messages
P2 = task events
P3 = tool output
P4 = logs
P5 = debug telemetry
```

---

# 55. Backpressure

System harus menghindari:

```text
fast producer
      |
      v
slow subscriber
      |
      v
unbounded memory
```

Gunakan:

- bounded queue
- backpressure
- drop policy untuk event non-critical
- persistence untuk event penting

---

# 56. Event Retention

Tidak semua event harus disimpan selamanya.

Contoh:

```text
debug logs:
1 hour

normal events:
30 days

task artifacts:
persistent

approval events:
persistent

audit events:
persistent
```

Retention configurable.

---
