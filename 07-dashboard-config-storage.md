<!-- Doc 07 — Dashboard, Config, Storage (§33–37)
     Bagian dari societas-full-product-spec. Urutan dokumen diatur di README.md.
     Nomor section dipertahankan; referensi silang antar-doc memakai nomor section (#N, 5A.x, 72A.x). -->

# 33. Dashboard

Dashboard adalah interface utama untuk melihat organisasi.

## 33.1 Organization View

```text
SOCIETAS

CEO        ● Working
CTO        ● Working
Research   ● Searching
Engineer   ● Coding
Reviewer   ○ Idle
```

---

## 33.2 Agent Detail

Menampilkan:

- role
- model
- status
- current task
- recent events
- memory
- tools
- permissions
- token usage
- artifacts

---

## 33.3 Task Board

View:

```text
Backlog
   |
   v
In Progress
   |
   v
Review
   |
   v
Done
```

Setiap kartu task aktif memiliki tombol kontrol UI:

```text
[ Pause ]   menjeda task (running -> paused)
[ Resume ]  melanjutkan task dengan context terakhir (paused -> running)
[ Cancel ]  membatalkan task permanen (-> cancelled)
```

Klik tombol mengirim **sinyal deterministik ke backend Go (0 token LLM)**. Kontrol yang sama tersedia via command tag di CLI/chat — backend mengintersepsi `#TASK-xxx pause` / `#TASK-xxx resume` secara deterministik tanpa memanggil LLM router.

Transisi yang diizinkan mengikuti state machine di 72A.6.

---

## 33.4 Agent Graph

Menampilkan hubungan:

```text
          CEO
       /   |   \
     CTO  CPO  Research
      |          |
    Coder       Analyst
      |
   Reviewer
```

---

## 33.5 Live Event Stream

Contoh:

```text
12:01:03 CEO -> Research
Research agent communication patterns

12:01:05 Research started

12:01:08 Research -> CEO
Found 7 relevant implementations

12:01:09 CEO -> CTO
Evaluate implementation #3

12:01:14 CTO started analysis
```

---

## 33.6 Artifact Explorer

User dapat melihat:

```text
Artifacts
├── research.md
├── architecture.md
├── benchmark.json
├── review.md
└── patch.diff
```

---

## 33.7 Approval Center

Semua action yang membutuhkan human approval.

```text
3 approvals pending

[Deploy staging]
[Run migration]
[Modify config]
```

---

# 36. Workspace Configuration

Contoh:

```yaml
version: "1"

workspace:
  name: "tunly-company"

server:
  host: "127.0.0.1"
  port: 7443

transport:
  event_bus: "go-channel"

agents:
  ceo:
    role: "CEO"
    model: "..."
    autonomy: 3
    permissions:
      filesystem: read

  cto:
    role: "CTO"
    model: "..."
    autonomy: 3

  research:
    role: "Research"
    model: "..."
    autonomy: 2
    tools:
      - browser
      - search

  engineer:
    role: "Engineer"
    model: "..."
    autonomy: 2
    prompt_template: "templates/engineer.yaml"   # Base Identity Template (5A.4)
    tools:
      - filesystem
      - shell
      - git

# Pengambil keputusan akhir debat/putusan teknis (#30.1, #48)
escalation_lead: "cto"        # atau "human" -> diserahkan ke dashboard

# Evaluasi risiko dinamis -> risk_tier / risk_tags task (#23.1, 72A.5)
# Toolchain deklaratif untuk Compiler Gate / Deterministic Toolchain Runner (5A.21)
toolchain:
  type: "rust"          # atau node, go, python (polyglot)
  shared_cache_dir: "/tmp/societas-cache/rust-shared"
  pipeline:             # fail-fast: berhenti di step pertama yang gagal
    - name: "format"
      cmd: "cargo fmt --check"
      parser: "regex"
    - name: "check"
      cmd: "cargo check --message-format=json"
      parser: "cargo_json"
    - name: "clippy"
      cmd: "cargo clippy --message-format=json -- -D warnings"
      parser: "cargo_json"
    - name: "test"
      cmd: "cargo nextest run"
      parser: "raw_tail"

risk:
  path_patterns:
    critical:
      - "migrations/**"
      - "infra/**"
      - "contracts/**"
    high:
      - "src/auth/**"
  intent_keywords:
    critical:
      - "drop database"
      - "payout"
    high:
      - "deploy"
      - "secret"
```

---

# 37. Storage

Penyimpanan dibagi menjadi dua pilar (Dual-Storage Architecture).

## 37.1 Operational Store — SQLite

Menyimpan data relasional dan operasional:

```text
agents
tasks (termasuk risk_tier, risk_tags)
events      (append-only event log)
messages
run history
approvals
artifact metadata
memory (entry terstruktur)
usage / akumulasi budget
```

File artifacts tetap disimpan sebagai files. Database hanya menyimpan metadata.

## 37.2 Cognitive Store — Embedded Vector DB

Menyimpan representasi semantik, bukan data operasional:

```text
embedding artifact (artifact.created)
ringkasan riset
koordinat semantik memory masa lalu
```

Implementasi: embedded vector DB seperti **ChromaDB** atau **`sqlite-vec`**, agar tetap local-first tanpa server eksternal. Embedding dihasilkan oleh model embedding lokal yang ringan — bukan model chat utama.

## 37.3 Pemisahan Tanggung Jawab

- Semantic Retrieval (5A.24) menanyakan Vector DB dan menerima ID referensi artifact/memory.
- SQLite tidak pernah dipakai untuk pencarian teks mentah atau `LIKE`.
- Vector DB tidak pernah dipakai untuk relasi data, status, atau ledger — itu tanggung jawab SQLite.

---
