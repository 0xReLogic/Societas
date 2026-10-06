<!-- Doc 10 — Contracts 72A + MVP & Roadmap (§72A–105)
     Bagian dari societas-full-product-spec. Urutan dokumen diatur di README.md.
     Nomor section dipertahankan; referensi silang antar-doc memakai nomor section (#N, 5A.x, 72A.x). -->

# 72A. Contracts & Schemas (Source of Truth)

Section ini adalah **satu-satunya definisi kanonik** bentuk data yang dipertukarkan di dalam Societas: envelope, event, task, budget, usage, artifact, summary, tool call, approval, dan error.

Jika contoh di section lain (misalnya #7, #10, #11, #63) berbeda dengan section ini, **Section 72A yang berlaku**.

Format: JSON Schema (draft 2020-12), netral terhadap bahasa. Implementasi (Go, TypeScript, dll.) sebaiknya **generate type dari schema ini** atau memvalidasinya saat runtime, bukan menulis ulang tangan.

Contoh di section ini divalidasi terhadap schema yang sama (lihat 72A.13).

## 72A.1 Aturan Dasar (Invariants)

Aturan ini ditegakkan oleh runtime, bukan oleh prompt agent.

| # | Aturan | Ditegakkan oleh |
|---|--------|-----------------|
| I1 | Agent **tidak memanggil agent lain secara langsung**. Semua pesan lewat Event Bus yang dimediasi Control Plane. | Event Bus + Policy Engine |
| I2 | Agent hanya boleh **meminta** pembuatan task (`task.delegate_requested`). Hanya Orchestrator yang membuat dan meng-assign task. | Orchestrator |
| I3 | Budget yang diberikan ke anak tidak boleh melebihi sisa budget parent. Total budget semua anak aktif tidak boleh melebihi sisa budget parent. | Budget Manager |
| I4 | Tidak ada model call tanpa `budget.reserved` dan keputusan policy `allow`. Setiap model call harus di-settle (`budget.settled`) dengan usage nyata. | Token Guard (5A.15) |
| I5 | Konten inline dibatasi (default: pesan 8.000 karakter, output tool 16.000 karakter). Yang lebih besar harus menjadi artifact + summary. | Event Bus |
| I6 | Event bersifat immutable dan append-only. Event store memberi `seq` yang naik monoton per run. | Event Store |
| I7 | `idempotency_key` yang sama dalam satu run diabaikan dan dijawab dengan hasil sebelumnya. | Event Bus |
| I8 | Setiap event punya `correlation_id` (konstan per permintaan user) dan `causation_id` (event penyebab), kecuali event root (`run.created`). | Event Bus |
| I9 | `type` tidak dikenal, atau payload yang tidak lolos schema, ditolak dengan `SCHEMA_VALIDATION_FAILED`. | Validator di boundary |
| I10 | Output LLM yang harus terstruktur (delegation, tool call) diparse sebagai JSON dan divalidasi. Jika gagal, agent diminta memperbaiki maksimal 2 kali, dihitung dalam retry budget. | Agent Runtime |
| I11 | Status task terminal (`completed`, `failed`, `cancelled`) bersifat final. Retry dilakukan lewat `running → ready`, bukan membuka task yang sudah `failed`. | Orchestrator |
| I12 | Pengecekan fan-out, depth, dan iterasi dilakukan saat `task.delegate_requested` diproses, sebelum task dibuat. | Orchestrator |
| I13 | Setiap run diakhiri tepat satu `run.stopped` dengan `reason` yang jelas. | Orchestrator |
| I14 | Agent tidak dapat mengubah budget, policy, atau limit miliknya sendiri. Hanya human (lewat approval) yang dapat menaikkannya. | Budget Manager + Policy Engine |
| I15 | Event wajib ter-commit ke Event Store (SQLite) **sebelum** disalurkan ke subscriber (transactional outbox, #42.1). Tidak ada delivery dari memory saja. | Event Bus + Event Store |

## 72A.2 Identifier & Addressing

| Jenis | Format | Contoh |
|-------|--------|--------|
| Workspace | `ws_<slug>` | `ws_acme` |
| Run | `RUN-<nomor>` | `RUN-001` |
| Task | `TASK-<nomor>` | `TASK-002` |
| Event | `evt_<ULID>` | `evt_01J9Z3K4M5N6P7Q8R9S0T1V2W3` |
| Message | `msg_<ULID>` | |
| Conversation | `conv_<ULID>` | |
| Artifact | `art_<ULID>` | |
| Summary | `sum_<ULID>` | |
| Tool call | `tc_<ULID>` | |
| Approval | `apr_<ULID>` | |
| Correlation | `cor_<ULID>` | |
| Agent | slug huruf kecil | `ceo`, `research` |

Nomor `RUN-` dan `TASK-` berurutan per workspace dan mudah dibaca manusia. ID lainnya memakai ULID (26 karakter Crockford base32) supaya urut waktu dan unik tanpa koordinasi.

Alamat (`from` / `to`) memakai format `<jenis>:<nama>`:

| Alamat envelope | Bentuk singkat di UI (#50) |
|-----------------|-------------------------------|
| `agent:ceo` | `@ceo` |
| `human:user` | pengguna |
| `system:orchestrator` | komponen Control Plane |
| `topic:all` | `@all` |
| (task) | `#TASK-001` (field `task_id`) |

Komponen `system:*` yang dikenal: `orchestrator`, `scheduler`, `budget`, `policy`, `context`, `router`, `summarizer`, `tool_runtime`, `event_bus`.

## 72A.3 Envelope

Semua pesan memakai satu envelope yang sama. Perbedaan hanya ada pada `type` dan `payload`.

<!-- schema:envelope -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:societas:1:envelope",
  "title": "Envelope",
  "type": "object",
  "additionalProperties": false,
  "required": ["protocol_version", "schema_version", "id", "type", "ts",
               "workspace_id", "run_id", "correlation_id", "from", "to", "payload"],
  "properties": {
    "protocol_version": { "const": "societas/1" },
    "schema_version": { "type": "string", "pattern": "^[0-9]+$" },
    "id": { "$ref": "urn:societas:1:common#/$defs/evt_id" },
    "type": { "type": "string", "pattern": "^[a-z]+(\\.[a-z_]+)+$" },
    "ts": { "$ref": "urn:societas:1:common#/$defs/ts" },
    "seq": { "type": "integer", "minimum": 1,
             "description": "Diisi Event Store, bukan pengirim." },
    "workspace_id": { "type": "string", "pattern": "^ws_[a-z0-9_-]{1,32}$" },
    "run_id": { "$ref": "urn:societas:1:common#/$defs/run_id" },
    "task_id": { "$ref": "urn:societas:1:common#/$defs/task_id" },
    "correlation_id": { "$ref": "urn:societas:1:common#/$defs/cor_id" },
    "causation_id": { "$ref": "urn:societas:1:common#/$defs/evt_id" },
    "idempotency_key": { "type": "string", "minLength": 1, "maxLength": 128 },
    "trace_id": { "type": "string", "pattern": "^[0-9a-f]{32}$" },
    "from": { "$ref": "urn:societas:1:common#/$defs/actor" },
    "to": { "$ref": "urn:societas:1:common#/$defs/address" },
    "payload": { "type": "object" }
  }
}
```

Catatan:

- `protocol_version`, `message_type`, dan `schema_version` pada #72 dipetakan ke `protocol_version`, `type`, dan `schema_version`.
- Frame transport pada #71 (`HELLO`, `AUTH`, `PUBLISH`, dst.) berada di bawah envelope ini. Envelope adalah isi dari frame `PUBLISH`, `TASK`, `MESSAGE`, dan `TOOL`.
- `payload` divalidasi lagi terhadap schema sesuai `type` (lihat registry di 72A.7).

## 72A.4 Common Definitions

<!-- schema:common -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:societas:1:common",
  "$defs": {
    "run_id":  { "type": "string", "pattern": "^RUN-[0-9]{3,}$" },
    "task_id": { "type": "string", "pattern": "^TASK-[0-9]{3,}$" },
    "evt_id":  { "type": "string", "pattern": "^evt_[0-9A-HJKMNP-TV-Z]{26}$" },
    "msg_id":  { "type": "string", "pattern": "^msg_[0-9A-HJKMNP-TV-Z]{26}$" },
    "conv_id": { "type": "string", "pattern": "^conv_[0-9A-HJKMNP-TV-Z]{26}$" },
    "art_id":  { "type": "string", "pattern": "^art_[0-9A-HJKMNP-TV-Z]{26}$" },
    "sum_id":  { "type": "string", "pattern": "^sum_[0-9A-HJKMNP-TV-Z]{26}$" },
    "tc_id":   { "type": "string", "pattern": "^tc_[0-9A-HJKMNP-TV-Z]{26}$" },
    "apr_id":  { "type": "string", "pattern": "^apr_[0-9A-HJKMNP-TV-Z]{26}$" },
    "cor_id":  { "type": "string", "pattern": "^cor_[0-9A-HJKMNP-TV-Z]{26}$" },
    "agent_id": { "type": "string", "pattern": "^[a-z][a-z0-9_-]{1,31}$" },
    "actor":   { "type": "string", "pattern": "^(agent|human|system):[a-z][a-z0-9_.-]{0,31}$" },
    "address": { "type": "string", "pattern": "^(agent|human|system|topic):[a-z][a-z0-9_.-]{0,31}$" },
    "ts":      { "type": "string", "format": "date-time" },
    "sha256":  { "type": "string", "pattern": "^sha256:[0-9a-f]{64}$" },
    "priority": { "enum": ["low", "normal", "high", "critical"] },
    "tier":    { "enum": ["cheap", "medium", "strong"] },
    "scope":   { "enum": ["workspace", "run", "task", "agent", "tool"] },
    "tool_name": { "type": "string", "pattern": "^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)+$" }
  }
}
```

## 72A.5 Core Objects

### Budget

Batas yang boleh diberikan ke workspace, run, task, atau agent. Semua field opsional. Field yang tidak ada berarti "ikut batas parent". Mengacu ke 5A.2, 5A.13, 5A.14, dan 5A.19.

<!-- schema:budget -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:societas:1:budget",
  "title": "Budget",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "max_input_tokens":    { "type": "integer", "minimum": 0 },
    "max_output_tokens":   { "type": "integer", "minimum": 0 },
    "max_total_tokens":    { "type": "integer", "minimum": 0 },
    "max_model_calls":     { "type": "integer", "minimum": 0 },
    "max_tool_calls":      { "type": "integer", "minimum": 0 },
    "max_agent_messages":  { "type": "integer", "minimum": 0 },
    "max_time_seconds":    { "type": "integer", "minimum": 0 },
    "max_cost_usd":        { "type": "number",  "minimum": 0 },
    "max_parallel_agents": { "type": "integer", "minimum": 0 },
    "max_child_tasks":     { "type": "integer", "minimum": 0 },
    "max_depth":           { "type": "integer", "minimum": 0 },
    "max_agent_iterations": { "type": "integer", "minimum": 0 },
    "max_task_iterations":  { "type": "integer", "minimum": 0 },
    "retry": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "max_attempts": { "type": "integer", "minimum": 0 },
        "max_total_retry_cost_usd": { "type": "number", "minimum": 0 }
      }
    }
  }
}
```

Aturan pemakaian budget:

- **Reserve lalu settle.** Sebelum model call, Budget Manager me-reserve batas atas (token dan biaya). Setelah selesai, usage nyata di-settle dan sisa reservasi dikembalikan.
- Budget bersifat hierarkis (5A.3): `workspace > run > task > agent > tool`.
- Peringatan dikirim saat 80% terpakai (`budget.warning`). Saat limit tercapai: `budget.exceeded`, lalu stop atau approval (5A.20).

### Usage

Pemakaian satu model call. Dicatat oleh Cost Tracker (5A.10).

<!-- schema:usage -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:societas:1:usage",
  "title": "Usage",
  "type": "object",
  "additionalProperties": false,
  "required": ["model", "input_tokens", "output_tokens", "duration_ms", "estimated_cost_usd"],
  "properties": {
    "provider": { "type": "string" },
    "model": { "type": "string" },
    "input_tokens": { "type": "integer", "minimum": 0 },
    "output_tokens": { "type": "integer", "minimum": 0 },
    "cached_input_tokens": { "type": "integer", "minimum": 0 },
    "duration_ms": { "type": "integer", "minimum": 0 },
    "estimated_cost_usd": { "type": "number", "minimum": 0 }
  }
}
```

### Usage Totals

Akumulasi pemakaian per scope (task, run, workspace).

<!-- schema:usage_totals -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:societas:1:usage_totals",
  "title": "UsageTotals",
  "type": "object",
  "additionalProperties": false,
  "required": ["input_tokens", "output_tokens", "model_calls", "tool_calls", "estimated_cost_usd"],
  "properties": {
    "input_tokens": { "type": "integer", "minimum": 0 },
    "output_tokens": { "type": "integer", "minimum": 0 },
    "model_calls": { "type": "integer", "minimum": 0 },
    "tool_calls": { "type": "integer", "minimum": 0 },
    "agent_messages": { "type": "integer", "minimum": 0 },
    "retries": { "type": "integer", "minimum": 0 },
    "estimated_cost_usd": { "type": "number", "minimum": 0 },
    "elapsed_seconds": { "type": "number", "minimum": 0 }
  }
}
```

### Error

Satu bentuk error untuk semua event gagal. Katalog kode ada di 72A.9.

<!-- schema:error -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:societas:1:error",
  "title": "Error",
  "type": "object",
  "additionalProperties": false,
  "required": ["code", "category", "message", "retryable"],
  "properties": {
    "code": { "type": "string", "pattern": "^[A-Z][A-Z0-9_]+$" },
    "category": { "enum": ["MODEL_ERROR", "TOOL_ERROR", "NETWORK_ERROR", "TIMEOUT",
                           "PERMISSION_DENIED", "INVALID_OUTPUT", "DEPENDENCY_FAILED",
                           "BUDGET_ERROR", "LIMIT_ERROR"] },
    "message": { "type": "string", "maxLength": 1000 },
    "retryable": { "type": "boolean" },
    "retry_after_ms": { "type": "integer", "minimum": 0 },
    "details": { "type": "object" }
  }
}
```

### Task

Bentuk lengkap task (memperluas #7).

<!-- schema:task -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:societas:1:task",
  "title": "Task",
  "type": "object",
  "additionalProperties": false,
  "required": ["id", "run_id", "parent_task_id", "title", "goal", "owner", "created_by",
               "priority", "status", "depth", "attempt", "expected_output", "budget",
               "created_at", "updated_at"],
  "properties": {
    "id": { "$ref": "urn:societas:1:common#/$defs/task_id" },
    "run_id": { "$ref": "urn:societas:1:common#/$defs/run_id" },
    "parent_task_id": { "oneOf": [ { "$ref": "urn:societas:1:common#/$defs/task_id" }, { "type": "null" } ] },
    "title": { "type": "string", "minLength": 1, "maxLength": 200 },
    "goal": { "type": "string", "minLength": 1, "maxLength": 4000 },
    "owner": { "$ref": "urn:societas:1:common#/$defs/agent_id" },
    "created_by": { "$ref": "urn:societas:1:common#/$defs/actor" },
    "priority": { "$ref": "urn:societas:1:common#/$defs/priority" },
    "status": { "enum": ["pending", "ready", "running", "pausing", "paused", "interrupted",
                         "blocked", "awaiting_approval", "completed", "failed", "cancelled"] },
    "dependencies": { "type": "array", "items": { "$ref": "urn:societas:1:common#/$defs/task_id" }, "uniqueItems": true },
    "deadline": { "oneOf": [ { "$ref": "urn:societas:1:common#/$defs/ts" }, { "type": "null" } ] },
    "depth": { "type": "integer", "minimum": 0 },
    "attempt": { "type": "integer", "minimum": 1 },
    "expected_output": {
      "type": "object",
      "additionalProperties": false,
      "required": ["kind"],
      "properties": {
        "kind": { "enum": ["artifact", "summary", "decision", "patch"] },
        "format": { "type": "string", "maxLength": 64 }
      }
    },
    "budget": {
      "type": "object",
      "additionalProperties": false,
      "required": ["granted", "used"],
      "properties": {
        "granted": { "$ref": "urn:societas:1:budget" },
        "used": { "$ref": "urn:societas:1:usage_totals" }
      }
    },
    "artifact_ids": { "type": "array", "items": { "$ref": "urn:societas:1:common#/$defs/art_id" } },
    "risk_tier": { "enum": ["low", "normal", "high", "critical"], "default": "normal",
                   "description": "Tier risiko dari evaluasi dinamis workspace.yaml (#23.1, #36); 'critical' memicu model tier tinggi, audit keamanan wajib, dan kunci mutasi hingga human approval (5A.8)." },
    "risk_tags": { "type": "array", "items": { "type": "string", "maxLength": 64 }, "uniqueItems": true,
                   "description": "Tag penyebab klasifikasi, mis. 'path:migrations/**', 'intent:deploy'." },
    "contract_hash": { "oneOf": [ { "$ref": "urn:societas:1:common#/$defs/sha256" }, { "type": "null" } ],
                       "description": "Pin SHA256 dari OpenAPI spec / Contract ABI untuk task contract-first (#17.1); task ditandai stale jika spec berubah." },
    "created_at": { "$ref": "urn:societas:1:common#/$defs/ts" },
    "updated_at": { "$ref": "urn:societas:1:common#/$defs/ts" }
  }
}
```

### Artifact Reference

Yang dikirim antar-agent adalah referensi, bukan isi (5A.6). Memperluas #17.

<!-- schema:artifact_ref -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:societas:1:artifact_ref",
  "title": "ArtifactRef",
  "type": "object",
  "additionalProperties": false,
  "required": ["id", "name", "kind", "checksum", "size_bytes", "version", "task_id", "created_by", "created_at"],
  "properties": {
    "id": { "$ref": "urn:societas:1:common#/$defs/art_id" },
    "name": { "type": "string", "minLength": 1, "maxLength": 255 },
    "kind": { "type": "string", "maxLength": 64,
              "description": "mis. markdown, json, diff, svg, text" },
    "path": { "type": "string", "maxLength": 1024 },
    "checksum": { "$ref": "urn:societas:1:common#/$defs/sha256" },
    "size_bytes": { "type": "integer", "minimum": 0 },
    "version": { "type": "integer", "minimum": 1 },
    "task_id": { "$ref": "urn:societas:1:common#/$defs/task_id" },
    "created_by": { "$ref": "urn:societas:1:common#/$defs/actor" },
    "created_at": { "$ref": "urn:societas:1:common#/$defs/ts" },
    "superseded_by": { "$ref": "urn:societas:1:common#/$defs/art_id",
                     "description": "opsional — tombstone #19.6; artifact basi, tidak boleh masuk context" },
    "staleness": { "type": "string", "enum": ["fresh", "stale"], "default": "fresh",
                   "description": "stale jika source_path/commit sudah tidak ada di main (#19.6)" },
    "source_path": { "type": "string", "maxLength": 1024,
                     "description": "path file repo sumber memori (#19.6)" },
    "source_commit": { "type": "string", "maxLength": 64 },
    "metadata": { "type": "object" }
  }
}
```

### Summary

Representasi ringkas dari artifact besar (5A.7). Wajib menunjuk artifact asli dan versinya.

<!-- schema:summary -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:societas:1:summary",
  "title": "Summary",
  "type": "object",
  "additionalProperties": false,
  "required": ["id", "artifact_id", "artifact_version", "token_estimate", "generated_by", "model", "body"],
  "properties": {
    "id": { "$ref": "urn:societas:1:common#/$defs/sum_id" },
    "artifact_id": { "$ref": "urn:societas:1:common#/$defs/art_id" },
    "artifact_version": { "type": "integer", "minimum": 1 },
    "token_estimate": { "type": "integer", "minimum": 0 },
    "generated_by": { "$ref": "urn:societas:1:common#/$defs/actor" },
    "model": { "type": "string" },
    "body": {
      "type": "object",
      "additionalProperties": false,
      "required": ["text"],
      "properties": {
        "text": { "type": "string", "maxLength": 8000 },
        "findings": { "type": "array", "items": { "type": "string" } },
        "risks": { "type": "array", "items": { "type": "string" } },
        "recommendation": { "type": "string" },
        "sources": { "type": "array", "items": { "type": "string" } }
      }
    }
  }
}
```

## 72A.6 Task State Machine

Status task:

```text
pending            dibuat, menunggu dependency atau scheduler
ready              dependency selesai, budget sudah di-reserve, menunggu slot agent
running            agent sedang bekerja
pausing            transisi menuju paused; menunggu LLM call in-flight selesai (cooperative pause)
paused             dijeda oleh pengguna; context terakhir dipertahankan untuk resume
interrupted        task berstatus running saat boot sistem; menunggu evaluasi Orchestrator
blocked            menunggu child task atau dependency saat berjalan
awaiting_approval  menunggu keputusan human
completed          selesai (terminal)
failed             gagal permanen (terminal)
cancelled          dibatalkan (terminal)
```

Transisi yang diizinkan (selain ini ditolak):

| Dari | Ke | Pemicu | Event |
|------|----|--------|-------|
| `pending` | `ready` | dependency selesai dan budget di-reserve | `task.assigned` |
| `pending` | `failed` | dependency gagal (`DEPENDENCY_FAILED`) | `task.failed` |
| `pending` | `cancelled` | dibatalkan | `task.cancelled` |
| `ready` | `running` | agent mulai | `task.started` |
| `ready` | `cancelled` | dibatalkan | `task.cancelled` |
| `running` | `blocked` | menunggu child task atau dependency | `task.blocked` |
| `running` | `awaiting_approval` | policy meminta approval; task diparkir, worker dilepas (step function, #40.1) | `approval.requested` |
| `running` | `paused` | klik pause di UI atau command tag `#TASK-xxx pause` (tanpa call in-flight) | `task.paused` |
| `running` | `pausing` | klik pause saat LLM/tool call masih in-flight | `task.paused` |
| `pausing` | `paused` | call in-flight selesai/di-settle | `task.paused` |
| `pausing` | `running` | pause dibatalkan sebelum settle | `task.resumed` |
| `paused` | `running` | klik resume di UI atau command tag `#TASK-xxx resume` | `task.resumed` |
| `paused` | `cancelled` | dibatalkan atau TTL paused habis | `task.cancelled` |
| `interrupted` | `running` | resume disetujui Orchestrator (CAS pada status stored) | `task.resumed` |
| `interrupted` | `ready` | dijadwalkan ulang oleh Orchestrator | `task.retry_scheduled` |
| `interrupted` | `failed` | tidak dapat dilanjutkan | `task.failed` |
| `interrupted` | `cancelled` | dibatalkan | `task.cancelled` |
| `running` | `completed` | output diterima | `task.completed` |
| `running` | `ready` | error yang bisa di-retry, masih ada retry budget (`attempt + 1`) | `task.retry_scheduled` |
| `running` | `failed` | error final atau retry habis | `task.failed` |
| `running` | `cancelled` | dibatalkan | `task.cancelled` |
| `blocked` | `running` | yang ditunggu selesai | `task.started` |
| `blocked` | `failed` | yang ditunggu gagal | `task.failed` |
| `blocked` | `cancelled` | dibatalkan | `task.cancelled` |
| `awaiting_approval` | `ready` | approval granted + `bound_hash` valid; CAS lalu reschedule (#40.1, #40.2) | `approval.granted` |
| `awaiting_approval` | `failed` | rejected atau timeout | `task.failed` |
| `awaiting_approval` | `cancelled` | dibatalkan | `task.cancelled` |

Resumption context: saat `paused -> running`, task **tidak dibuat ulang** — `id` tetap sama, budget tracking melanjutkan `budget.used` sebelumnya, dan Context Manager mengambil progress terakhir dari artefak tersimpan di Operational Store (SQLite, #37.1).

**Cooperative pause (`pausing`):** pause tidak memotong LLM/tool call yang sedang in-flight — call dibiarkan settle dulu (usage-nya tetap dicatat), baru status menjadi `paused`. Ini menjaga konsistensi `budget.reserved`/`budget.settled` (I4).

**Startup recovery (`interrupted`):** saat boot, semua task berstatus `running` di SQLite diubah menjadi `interrupted`. Orchestrator mengevaluasi tiap task — resume, retry ke `ready`, atau `failed` — memakai Optimistic Concurrency Control (CAS pada status stored) agar evaluasi tidak bentrok dengan writer lain.

**Paused TTL:** task `paused` membawa TTL; habis masa berlaku -> `cancelled`. Ini mencegah task jeda menahan worktree (#60.1) dan alokasi `budget.reserved` selamanya.

## 72A.7 Event Registry

Memperluas daftar event di #11. Setiap `type` punya tepat satu schema payload. Event di luar tabel ini ditolak (I9).

| `type` | Schema payload | Dari → Ke |
|--------|----------------|-----------|
| `workspace.created` | `workspace_created` | `system:*` → `topic:all` |
| `agent.created` | `agent_lifecycle` | `system:orchestrator` → `topic:all` |
| `agent.started` | `agent_lifecycle` | `system:scheduler` → `topic:all` |
| `agent.stopped` | `agent_lifecycle` | `system:scheduler` → `topic:all` |
| `run.created` | `run_created` | `human` → `system:orchestrator` |
| `run.stopped` | `run_stopped` | `system:orchestrator` → `human` |
| `task.delegate_requested` | `delegate_requested` | `agent` → `system:orchestrator` |
| `task.delegate_rejected` | `delegate_rejected` | `system:orchestrator` → `agent` |
| `task.created` | `task_created` | `system:orchestrator` → `agent` (owner) |
| `task.assigned` | `task_assigned` | `system:scheduler` → `agent` |
| `task.started` | `task_started` | `agent` → `system:orchestrator` |
| `task.blocked` | `task_blocked` | `agent` → `system:orchestrator` |
| `task.paused` | `task_paused` | `human` → `system:orchestrator` |
| `task.resumed` | `task_resumed` | `system:orchestrator` → `agent` |
| `task.completed` | `task_completed` | `agent` → `system:orchestrator` |
| `task.failed` | `task_failed` | `system:orchestrator` → `topic:all` |
| `task.cancelled` | `task_cancelled` | `system:orchestrator` → `topic:all` |
| `task.retry_scheduled` | `task_retry_scheduled` | `system:orchestrator` → `agent` |
| `message.sent` | `message_sent` | `agent` → `agent` (dimediasi Event Bus) |
| `message.received` | `message_received` | `agent` → `system:event_bus` |
| `context.built` | `context_built` | `system:context` → `agent` |
| `model.selected` | `model_selected` | `system:router` → `agent` |
| `model.call_started` | `model_call_started` | `system:router` → `topic:all` |
| `model.call_completed` | `model_call_completed` | `system:router` → `agent` |
| `model.call_failed` | `model_call_failed` | `system:router` → `agent` |
| `budget.reserved` | `budget_reserved` | `system:budget` → `topic:all` |
| `budget.settled` | `budget_settled` | `system:budget` → `topic:all` |
| `budget.warning` | `budget_warning` | `system:budget` → `human` |
| `budget.exceeded` | `budget_exceeded` | `system:budget` → `system:orchestrator` |
| `policy.evaluated` | `policy_evaluated` | `system:policy` → `topic:all` |
| `tool.call_requested` | `tool_call_requested` | `agent` → `system:tool_runtime` |
| `tool.call_started` | `tool_call_started` | `system:tool_runtime` → `topic:all` |
| `tool.call_completed` | `tool_call_completed` | `system:tool_runtime` → `agent` |
| `tool.call_failed` | `tool_call_failed` | `system:tool_runtime` → `agent` |
| `artifact.created` | `artifact_created` | `agent` → `topic:all` |
| `artifact.updated` | `artifact_updated` | `agent` → `topic:all` |
| `summary.created` | `summary_created` | `system:summarizer` → `topic:all` |
| `review.requested` | `review_requested` | `agent` → `system:orchestrator` |
| `review.completed` | `review_completed` | `agent` → `system:orchestrator` |
| `approval.requested` | `approval_requested` | `system:policy` → `human` |
| `approval.granted` | `approval_granted` | `human` → `system:policy` |
| `approval.rejected` | `approval_rejected` | `human` → `system:policy` |

## 72A.8 Payload Schemas

### Run

<!-- schemas:run -->
```json
[
  {
    "$id": "urn:societas:1:run_created",
    "type": "object", "additionalProperties": false, "required": ["goal"],
    "properties": {
      "goal": { "type": "string", "minLength": 1, "maxLength": 4000 },
      "entry_agent": { "$ref": "urn:societas:1:common#/$defs/agent_id" },
      "budget_request": { "$ref": "urn:societas:1:budget" }
    }
  },
  {
    "$id": "urn:societas:1:run_stopped",
    "type": "object", "additionalProperties": false, "required": ["reason", "totals"],
    "properties": {
      "reason": { "enum": ["success", "budget_exhausted", "timeout", "human_rejected",
                           "critical_tool_failure", "dependency_failed",
                           "max_iterations", "cancelled_by_user"] },
      "totals": { "$ref": "urn:societas:1:usage_totals" },
      "result_artifact_id": { "$ref": "urn:societas:1:common#/$defs/art_id" },
      "error": { "$ref": "urn:societas:1:error" }
    }
  },
  {
    "$id": "urn:societas:1:workspace_created",
    "type": "object", "additionalProperties": false, "required": ["name"],
    "properties": { "name": { "type": "string", "minLength": 1, "maxLength": 100 } }
  },
  {
    "$id": "urn:societas:1:agent_lifecycle",
    "type": "object", "additionalProperties": false, "required": ["agent_id"],
    "properties": {
      "agent_id": { "$ref": "urn:societas:1:common#/$defs/agent_id" },
      "reason": { "type": "string", "maxLength": 500 }
    }
  }
]
```

### Delegation

Agent hanya **meminta**. `budget_request` adalah permintaan, bukan pemberian. Budget yang sebenarnya muncul di `task.created` (`task.budget.granted`), dan tidak pernah lebih besar dari sisa parent (I3).

`rationale` wajib. Ini yang membuat workflow bisa menjawab "mengapa agent ini dipanggil" (lihat #105).

<!-- schemas:delegation -->
```json
[
  {
    "$id": "urn:societas:1:delegate_requested",
    "type": "object", "additionalProperties": false,
    "required": ["title", "goal", "rationale", "expected_output", "priority"],
    "properties": {
      "title": { "type": "string", "minLength": 1, "maxLength": 200 },
      "goal": { "type": "string", "minLength": 1, "maxLength": 4000 },
      "rationale": { "type": "string", "minLength": 1, "maxLength": 1000 },
      "requested_assignee": {
        "oneOf": [
          { "$ref": "urn:societas:1:common#/$defs/agent_id" },
          { "type": "null" }
        ],
        "description": "ID agen tujuan — divalidasi terhadap enum dinamis ID agen aktif workspace.yaml (constrained decoding, 5A.8). null = Blind Delegation: sistem yang menentukan eksekutor terbaik via Jev AI (72A.10)."
      },
      "expected_output": {
        "type": "object", "additionalProperties": false, "required": ["kind"],
        "properties": {
          "kind": { "enum": ["artifact", "summary", "decision", "patch"] },
          "format": { "type": "string", "maxLength": 64 }
        }
      },
      "priority": { "$ref": "urn:societas:1:common#/$defs/priority" },
      "complexity_hint": { "enum": ["low", "medium", "high"] },
      "dependencies": { "type": "array", "uniqueItems": true,
                        "items": { "$ref": "urn:societas:1:common#/$defs/task_id" } },
      "deadline": { "$ref": "urn:societas:1:common#/$defs/ts" },
      "context_hints": {
        "type": "object", "additionalProperties": false,
        "properties": {
          "artifact_ids": { "type": "array", "items": { "$ref": "urn:societas:1:common#/$defs/art_id" } },
          "memory_queries": { "type": "array", "maxItems": 5, "items": { "type": "string", "maxLength": 200 } }
        }
      },
      "budget_request": { "$ref": "urn:societas:1:budget" }
    }
  },
  {
    "$id": "urn:societas:1:delegate_rejected",
    "type": "object", "additionalProperties": false, "required": ["request_event_id", "error"],
    "properties": {
      "request_event_id": { "$ref": "urn:societas:1:common#/$defs/evt_id" },
      "error": { "$ref": "urn:societas:1:error" }
    }
  },
  {
    "$id": "urn:societas:1:task_created",
    "type": "object", "additionalProperties": false, "required": ["task"],
    "properties": { "task": { "$ref": "urn:societas:1:task" } }
  },
  {
    "$id": "urn:societas:1:task_assigned",
    "type": "object", "additionalProperties": false, "required": ["task_id", "agent_id"],
    "properties": {
      "task_id": { "$ref": "urn:societas:1:common#/$defs/task_id" },
      "agent_id": { "$ref": "urn:societas:1:common#/$defs/agent_id" }
    }
  }
]
```

### Task Lifecycle

<!-- schemas:task_lifecycle -->
```json
[
  {
    "$id": "urn:societas:1:task_started",
    "type": "object", "additionalProperties": false, "required": ["attempt"],
    "properties": { "attempt": { "type": "integer", "minimum": 1 } }
  },
  {
    "$id": "urn:societas:1:task_blocked",
    "type": "object", "additionalProperties": false, "required": ["waiting_on"],
    "properties": {
      "waiting_on": {
        "type": "array", "minItems": 1,
        "items": { "oneOf": [ { "$ref": "urn:societas:1:common#/$defs/task_id" },
                              { "$ref": "urn:societas:1:common#/$defs/apr_id" } ] }
      }
    }
  },
  {
    "$id": "urn:societas:1:task_completed",
    "type": "object", "additionalProperties": false, "required": ["result_status"],
    "properties": {
      "result_status": { "enum": ["success", "partial"] },
      "artifact_ids": { "type": "array", "items": { "$ref": "urn:societas:1:common#/$defs/art_id" } },
      "summary_ids": { "type": "array", "items": { "$ref": "urn:societas:1:common#/$defs/sum_id" } },
      "usage": { "$ref": "urn:societas:1:usage_totals" }
    }
  },
  {
    "$id": "urn:societas:1:task_failed",
    "type": "object", "additionalProperties": false, "required": ["error"],
    "properties": {
      "error": { "$ref": "urn:societas:1:error" },
      "usage": { "$ref": "urn:societas:1:usage_totals" }
    }
  },
  {
    "$id": "urn:societas:1:task_cancelled",
    "type": "object", "additionalProperties": false, "required": ["cancelled_by"],
    "properties": {
      "cancelled_by": { "$ref": "urn:societas:1:common#/$defs/actor" },
      "reason": { "type": "string", "maxLength": 500 }
    }
  },
  {
    "$id": "urn:societas:1:task_retry_scheduled",
    "type": "object", "additionalProperties": false, "required": ["attempt", "delay_ms", "error"],
    "properties": {
      "attempt": { "type": "integer", "minimum": 2 },
      "delay_ms": { "type": "integer", "minimum": 0 },
      "error": { "$ref": "urn:societas:1:error" }
    }
  }
]
```

### Messaging

Percakapan antar-agent (#16) tetap ada, tetapi dimediasi Event Bus (I1), dibatasi `max_agent_messages`, dan konten besar harus menjadi artifact (I5).

<!-- schemas:messaging -->
```json
[
  {
    "$id": "urn:societas:1:message_sent",
    "type": "object", "additionalProperties": false,
    "required": ["message_id", "conversation_id", "text"],
    "properties": {
      "message_id": { "$ref": "urn:societas:1:common#/$defs/msg_id" },
      "conversation_id": { "$ref": "urn:societas:1:common#/$defs/conv_id" },
      "text": { "type": "string", "minLength": 1, "maxLength": 8000 },
      "priority": { "$ref": "urn:societas:1:common#/$defs/priority" },
      "artifact_ids": { "type": "array", "items": { "$ref": "urn:societas:1:common#/$defs/art_id" } },
      "reply_to": { "$ref": "urn:societas:1:common#/$defs/msg_id" },
      "expects_reply": { "type": "boolean" }
    }
  },
  {
    "$id": "urn:societas:1:message_received",
    "type": "object", "additionalProperties": false, "required": ["message_id"],
    "properties": { "message_id": { "$ref": "urn:societas:1:common#/$defs/msg_id" } }
  }
]
```

### Control Plane

<!-- schemas:control_plane -->
```json
[
  {
    "$id": "urn:societas:1:context_built",
    "type": "object", "additionalProperties": false,
    "required": ["agent_id", "token_budget", "tokens_used", "items"],
    "properties": {
      "agent_id": { "$ref": "urn:societas:1:common#/$defs/agent_id" },
      "token_budget": { "type": "integer", "minimum": 1 },
      "tokens_used": { "type": "integer", "minimum": 0 },
      "items": {
        "type": "array",
        "items": {
          "type": "object", "additionalProperties": false,
          "required": ["kind", "ref", "tokens", "reason"],
          "properties": {
            "kind": { "enum": ["system_prompt", "role", "task", "memory", "artifact", "message", "tool_result"] },
            "ref": { "type": "string", "maxLength": 200 },
            "tokens": { "type": "integer", "minimum": 0 },
            "reason": { "type": "string", "maxLength": 300 }
          }
        }
      },
      "dropped": {
        "type": "array",
        "items": {
          "type": "object", "additionalProperties": false,
          "required": ["kind", "ref", "reason"],
          "properties": {
            "kind": { "type": "string" },
            "ref": { "type": "string", "maxLength": 200 },
            "reason": { "enum": ["over_budget", "low_relevance", "duplicate", "untrusted"] }
          }
        }
      }
    }
  },
  {
    "$id": "urn:societas:1:model_selected",
    "type": "object", "additionalProperties": false,
    "required": ["agent_id", "model", "tier", "reason"],
    "properties": {
      "agent_id": { "$ref": "urn:societas:1:common#/$defs/agent_id" },
      "model": { "type": "string" },
      "tier": { "$ref": "urn:societas:1:common#/$defs/tier" },
      "reason": { "type": "string", "maxLength": 300 },
      "escalated_from": { "type": ["string", "null"] }
    }
  },
  {
    "$id": "urn:societas:1:model_call_started",
    "type": "object", "additionalProperties": false, "required": ["model", "tier", "reservation_id"],
    "properties": {
      "model": { "type": "string" },
      "tier": { "$ref": "urn:societas:1:common#/$defs/tier" },
      "reservation_id": { "type": "string" }
    }
  },
  {
    "$id": "urn:societas:1:model_call_completed",
    "type": "object", "additionalProperties": false, "required": ["usage", "finish_reason"],
    "properties": {
      "usage": { "$ref": "urn:societas:1:usage" },
      "finish_reason": { "enum": ["stop", "length", "tool_use", "error"] },
      "confidence": { "type": "number", "minimum": 0, "maximum": 1 }
    }
  },
  {
    "$id": "urn:societas:1:model_call_failed",
    "type": "object", "additionalProperties": false, "required": ["error", "executed"],
    "properties": {
      "error": { "$ref": "urn:societas:1:error" },
      "executed": { "type": "boolean",
                    "description": "false jika Token Guard menolak sebelum model dipanggil." }
    }
  },
  {
    "$id": "urn:societas:1:budget_reserved",
    "type": "object", "additionalProperties": false,
    "required": ["scope", "scope_id", "reservation_id", "max_tokens", "max_cost_usd"],
    "properties": {
      "scope": { "$ref": "urn:societas:1:common#/$defs/scope" },
      "scope_id": { "type": "string" },
      "reservation_id": { "type": "string" },
      "max_tokens": { "type": "integer", "minimum": 0 },
      "max_cost_usd": { "type": "number", "minimum": 0 }
    }
  },
  {
    "$id": "urn:societas:1:budget_settled",
    "type": "object", "additionalProperties": false,
    "required": ["scope", "scope_id", "reservation_id", "usage", "remaining"],
    "properties": {
      "scope": { "$ref": "urn:societas:1:common#/$defs/scope" },
      "scope_id": { "type": "string" },
      "reservation_id": { "type": "string" },
      "usage": { "$ref": "urn:societas:1:usage" },
      "remaining": {
        "type": "object", "additionalProperties": false,
        "properties": {
          "total_tokens": { "type": "integer", "minimum": 0 },
          "cost_usd": { "type": "number", "minimum": 0 },
          "model_calls": { "type": "integer", "minimum": 0 }
        }
      }
    }
  },
  {
    "$id": "urn:societas:1:budget_warning",
    "type": "object", "additionalProperties": false,
    "required": ["scope", "scope_id", "threshold", "used_ratio"],
    "properties": {
      "scope": { "$ref": "urn:societas:1:common#/$defs/scope" },
      "scope_id": { "type": "string" },
      "threshold": { "type": "number", "minimum": 0, "maximum": 1 },
      "used_ratio": { "type": "number", "minimum": 0 }
    }
  },
  {
    "$id": "urn:societas:1:budget_exceeded",
    "type": "object", "additionalProperties": false,
    "required": ["scope", "scope_id", "limit", "error"],
    "properties": {
      "scope": { "$ref": "urn:societas:1:common#/$defs/scope" },
      "scope_id": { "type": "string" },
      "limit": { "type": "string", "pattern": "^max_[a-z_]+$" },
      "error": { "$ref": "urn:societas:1:error" }
    }
  },
  {
    "$id": "urn:societas:1:policy_evaluated",
    "type": "object", "additionalProperties": false,
    "required": ["action", "decision", "rule_id", "reason"],
    "properties": {
      "action": { "type": "string", "maxLength": 200,
                  "description": "mis. tool.call:shell.exec, agent.create, network.access" },
      "decision": { "enum": ["allow", "require_approval", "deny"] },
      "rule_id": { "type": "string", "maxLength": 100 },
      "reason": { "type": "string", "maxLength": 500 },
      "approval_id": { "$ref": "urn:societas:1:common#/$defs/apr_id" }
    }
  }
]
```

### Tool Call

Memperluas #63. Output besar tidak boleh inline: simpan sebagai artifact dan isi `output_artifact_id`.

<!-- schemas:tool -->
```json
[
  {
    "$id": "urn:societas:1:tool_call_requested",
    "type": "object", "additionalProperties": false,
    "required": ["tool_call_id", "tool", "arguments"],
    "properties": {
      "tool_call_id": { "$ref": "urn:societas:1:common#/$defs/tc_id" },
      "tool": { "$ref": "urn:societas:1:common#/$defs/tool_name" },
      "arguments": { "type": "object" },
      "timeout_ms": { "type": "integer", "minimum": 1 }
    }
  },
  {
    "$id": "urn:societas:1:tool_call_started",
    "type": "object", "additionalProperties": false, "required": ["tool_call_id"],
    "properties": { "tool_call_id": { "$ref": "urn:societas:1:common#/$defs/tc_id" } }
  },
  {
    "$id": "urn:societas:1:tool_call_completed",
    "type": "object", "additionalProperties": false,
    "required": ["tool_call_id", "status", "duration_ms"],
    "properties": {
      "tool_call_id": { "$ref": "urn:societas:1:common#/$defs/tc_id" },
      "status": { "enum": ["ok", "error"] },
      "output": { "type": ["string", "object"], "maxLength": 16000 },
      "output_artifact_id": { "$ref": "urn:societas:1:common#/$defs/art_id" },
      "truncated": { "type": "boolean" },
      "duration_ms": { "type": "integer", "minimum": 0 },
      "error": { "$ref": "urn:societas:1:error" }
    },
    "if": { "properties": { "status": { "const": "error" } }, "required": ["status"] },
    "then": { "required": ["error"] }
  },
  {
    "$id": "urn:societas:1:tool_call_failed",
    "type": "object", "additionalProperties": false, "required": ["tool_call_id", "error"],
    "properties": {
      "tool_call_id": { "$ref": "urn:societas:1:common#/$defs/tc_id" },
      "error": { "$ref": "urn:societas:1:error" },
      "duration_ms": { "type": "integer", "minimum": 0 }
    }
  }
]
```

`tool.call_completed` dengan `status: "error"` dipakai untuk tool yang berjalan tetapi mengembalikan hasil gagal secara logis (misalnya exit code non-nol). `tool.call_failed` dipakai ketika tool tidak bisa dijalankan sama sekali (ditolak policy, timeout, runtime error).

### Artifact, Summary, Review

<!-- schemas:artifact_review -->
```json
[
  {
    "$id": "urn:societas:1:artifact_created",
    "type": "object", "additionalProperties": false, "required": ["artifact"],
    "properties": { "artifact": { "$ref": "urn:societas:1:artifact_ref" } }
  },
  {
    "$id": "urn:societas:1:artifact_updated",
    "type": "object", "additionalProperties": false, "required": ["artifact", "previous_version"],
    "properties": {
      "artifact": { "$ref": "urn:societas:1:artifact_ref" },
      "previous_version": { "type": "integer", "minimum": 1 }
    }
  },
  {
    "$id": "urn:societas:1:summary_created",
    "type": "object", "additionalProperties": false, "required": ["summary"],
    "properties": { "summary": { "$ref": "urn:societas:1:summary" } }
  },
  {
    "$id": "urn:societas:1:review_requested",
    "type": "object", "additionalProperties": false, "required": ["artifact_ids"],
    "properties": {
      "artifact_ids": { "type": "array", "minItems": 1, "items": { "$ref": "urn:societas:1:common#/$defs/art_id" } },
      "criteria": { "type": "array", "items": { "type": "string", "maxLength": 300 } }
    }
  },
  {
    "$id": "urn:societas:1:review_completed",
    "type": "object", "additionalProperties": false, "required": ["verdict"],
    "properties": {
      "verdict": { "enum": ["approve", "request_changes", "reject"] },
      "findings": {
        "type": "array",
        "items": {
          "type": "object", "additionalProperties": false, "required": ["severity", "text"],
          "properties": {
            "severity": { "enum": ["info", "minor", "major", "blocker"] },
            "text": { "type": "string", "maxLength": 1000 }
          }
        }
      },
      "artifact_id": { "$ref": "urn:societas:1:common#/$defs/art_id" }
    }
  }
]
```

### Approval

Memperluas #23 dan 5A.20. Pilihan human dipetakan ke `scope`:

| Pilihan di UI | `decision` | `scope` |
|---------------|-----------|---------|
| Approve Once | `approval.granted` | `once` (hanya aksi ini) |
| Approve For Task | `approval.granted` | `task` (aksi sejenis dalam task ini) |
| Approve | `approval.granted` | `run` (aksi sejenis dalam run ini) |
| Reject | `approval.rejected` | n/a |

Untuk approval yang dipicu budget, human boleh menyertakan `budget_override`. Hanya jalur ini yang dapat menaikkan budget (I14).

<!-- schemas:approval -->
```json
[
  {
    "$id": "urn:societas:1:approval_requested",
    "type": "object", "additionalProperties": false,
    "required": ["approval_id", "action", "reason", "trigger", "risk", "bound_hash"],
    "properties": {
      "approval_id": { "$ref": "urn:societas:1:common#/$defs/apr_id" },
      "action": { "type": "string", "maxLength": 200 },
      "reason": { "type": "string", "maxLength": 1000 },
      "trigger": { "enum": ["policy", "budget"] },
      "risk": { "enum": ["low", "medium", "high"] },
      "bound_hash": { "$ref": "urn:societas:1:common#/$defs/sha256",
                      "description": "Hash kondisi saat request dibuat (commit SHA / migration hash). Jika berubah selama task diparkir, approval invalid (#40.2)." },
      "details": { "type": "object" },
      "expires_at": { "$ref": "urn:societas:1:common#/$defs/ts" }
    }
  },
  {
    "$id": "urn:societas:1:approval_granted",
    "type": "object", "additionalProperties": false,
    "required": ["approval_id", "scope", "granted_by"],
    "properties": {
      "approval_id": { "$ref": "urn:societas:1:common#/$defs/apr_id" },
      "scope": { "enum": ["once", "task", "run"] },
      "granted_by": { "$ref": "urn:societas:1:common#/$defs/actor" },
      "budget_override": { "$ref": "urn:societas:1:budget" }
    }
  },
  {
    "$id": "urn:societas:1:approval_rejected",
    "type": "object", "additionalProperties": false, "required": ["approval_id"],
    "properties": {
      "approval_id": { "$ref": "urn:societas:1:common#/$defs/apr_id" },
      "rejected_by": { "$ref": "urn:societas:1:common#/$defs/actor" },
      "reason": { "type": "string", "maxLength": 1000 }
    }
  }
]
```

## 72A.9 Error Catalog

Menggabungkan kategori di #44 dengan kode di 5A.15. Satu kode punya satu kategori, status `retryable`, dan satu aksi default. Retry selalu dihitung dalam retry budget (5A.13).

| Kode | Kategori | `retryable` | Aksi default |
|------|----------|-------------|--------------|
| `BUDGET_EXCEEDED` | `BUDGET_ERROR` | tidak | Model call tidak dijalankan. Emit `budget.exceeded` (`details.scope` menunjukkan level), lalu stop atau minta approval. |
| `CONTEXT_TOO_LARGE` | `LIMIT_ERROR` | tidak | Context Manager menyusun ulang dengan seleksi lebih ketat, maksimal 1 kali. Jika masih gagal, task gagal. |
| `RATE_LIMITED` | `LIMIT_ERROR` | ya | Tunggu `retry_after_ms`, retry terbatas. |
| `POLICY_DENIED` | `PERMISSION_DENIED` | tidak | Jangan retry. Agent diberi tahu dan dapat memilih jalur lain. |
| `APPROVAL_REJECTED` | `PERMISSION_DENIED` | tidak | Task `failed` atau agent mengambil jalur alternatif. |
| `APPROVAL_TIMEOUT` | `TIMEOUT` | tidak | Task `failed`. Human dapat memulai ulang. |
| `FANOUT_LIMIT_EXCEEDED` | `LIMIT_ERROR` | tidak | `task.delegate_rejected`. Agent harus menggabungkan pekerjaan. |
| `MAX_DEPTH_EXCEEDED` | `LIMIT_ERROR` | tidak | `task.delegate_rejected`. |
| `MAX_ITERATIONS_EXCEEDED` | `LIMIT_ERROR` | tidak | Task `failed`. Run dapat berhenti dengan `max_iterations`. |
| `MODEL_TIMEOUT` | `TIMEOUT` | ya | Retry terbatas, boleh escalate model. |
| `MODEL_UNAVAILABLE` | `MODEL_ERROR` | ya | Retry terbatas atau fallback ke provider/model lain. |
| `INVALID_OUTPUT` | `INVALID_OUTPUT` | ya | Agent correction, maksimal 2 kali (I10). |
| `TOOL_INPUT_INVALID` | `INVALID_OUTPUT` | ya | Agent correction dengan pesan error dari tool schema. |
| `TOOL_FAILED` | `TOOL_ERROR` | tergantung tool | Retry hanya jika tool idempotent. |
| `TOOL_TIMEOUT` | `TIMEOUT` | ya | Retry terbatas. |
| `NETWORK_ERROR` | `NETWORK_ERROR` | ya | Retry dengan backoff, terbatas. |
| `DEPENDENCY_FAILED` | `DEPENDENCY_FAILED` | tidak | Task `failed` dengan referensi task yang gagal di `details`. |
| `SCHEMA_VALIDATION_FAILED` | `INVALID_OUTPUT` | tidak | Pesan ditolak di boundary. Ini bug pengirim, bukan masalah sementara. |

Aturan:

- Kode baru wajib ditambahkan ke tabel ini sebelum dipakai.
- `retryable: true` hanya berarti **boleh** di-retry. Keputusan akhir tetap di Orchestrator berdasarkan retry budget.
- `INVALID_OUTPUT` pada model yang murah boleh memicu model escalation (5A.9) sebelum menghabiskan batas koreksi.

## 72A.10 Alur Baku

Urutan di bawah ini adalah kontrak perilaku. Urutan event harus sesuai.

### Model call (Token Guard, 5A.15)

```text
1. Agent Runtime butuh model call untuk task T
2. context.built          Context Manager menyusun context sesuai token_budget
3. check_budget           (gagal -> model.call_failed BUDGET_EXCEEDED, executed=false)
4. check_context_size     (gagal -> model.call_failed CONTEXT_TOO_LARGE, executed=false)
5. check_rate_limit       (gagal -> model.call_failed RATE_LIMITED, executed=false)
6. policy.evaluated       action="model.call", decision harus allow
7. model.selected         Model Router memilih tier dan model, dengan reason
8. budget.reserved        batas atas token dan biaya di-reserve
9. model.call_started
10. model.call_completed  (atau model.call_failed dengan executed=true)
11. budget.settled        usage nyata di-settle, sisa reservasi dikembalikan
12. (jika used_ratio >= 0.8) budget.warning
```

### Delegation (5A.1, I2, I12)

```text
1. Agent menghasilkan JSON delegasi, divalidasi sebagai delegate_requested (I10)
2. Event task.delegate_requested: agent -> system:orchestrator
3. Orchestrator memeriksa berurutan:
     a. fan-out    jumlah anak < max_child_tasks     (FANOUT_LIMIT_EXCEEDED)
     b. depth      depth parent + 1 <= max_depth     (MAX_DEPTH_EXCEEDED)
     c. dependency valid dan tidak membentuk siklus  (SCHEMA_VALIDATION_FAILED)
     d. policy     agent.create / assignment diizinkan (POLICY_DENIED)
     e. budget     grant <= sisa parent, lalu reserve  (BUDGET_EXCEEDED)
4. Memilih assignee:
     a. `requested_assignee` terisi valid (lolos enum dinamis)
        -> langsung task.created ke agen itu, tanpa LLM router (0 token)
     b. `requested_assignee` = null (Blind Delegation)
        -> Orchestrator memanggil Jev AI (Choice, ~150ms) untuk memilih
           agen paling cocok dari squad aktif
     c. `task.delegate_rejected` hanya rem darurat saat limit
        (fan-out/depth/budget) terlampaui — BUKAN karena salah nama agen
        (enum dinamis + constrained decoding membuatnya mustahil, 5A.8)
5. Sukses: task.created (budget granted terisi) lalu task.assigned
   Gagal:  task.delegate_rejected ke pengirim, dengan Error dari katalog
```

### Tool call

```text
1. tool.call_requested   agent -> system:tool_runtime
2. policy.evaluated      Jev AI mengevaluasi risiko tindakan -> (allow | require_approval | deny)
     deny             -> tool.call_failed POLICY_DENIED
     require_approval -> approval.requested, task awaiting_approval
                         granted  -> lanjut ke langkah 3
                         rejected -> tool.call_failed APPROVAL_REJECTED
3. tool.call_started
4. tool.call_completed | tool.call_failed
5. Output di atas batas inline -> simpan artifact, isi output_artifact_id
```

### Review (Local Compiler Gate, 5A.21)

```text
1. Engineer selesai -> artifact.created (patch/code)
2. backend Go menjalankan build/linter lokal (0 token):
     gagal -> task kembali ke Engineer dengan error log (tanpa LLM review)
3. lolos  -> review_requested -> Reviewer LLM
4. review_completed (approve | request_changes | reject)
     request_changes -> rebuttal max 2 putaran (#48)
```

### Output besar (5A.6, 5A.7)

```text
1. Agent selesai menulis output besar -> artifact.created
2. system:summarizer (model cheap) membuat ringkasan -> summary.created
3. Agent lain menerima summary + artifact_id, bukan isi penuh
4. Isi artifact hanya diambil jika benar-benar diperlukan
```

### Approval karena budget (5A.20)

```text
1. budget.exceeded
2. approval.requested (trigger="budget")
3. Human memilih:
     approval.granted (+ budget_override opsional) -> lanjut
     approval.rejected                             -> task failed, run.stopped (human_rejected)
```

## 72A.11 Walkthrough End-to-End

Skenario dari 5A.22. User meminta: *"CEO, evaluasi apakah kita perlu menambahkan fitur baru."*

Urutan event (ringkas):

| # | Event | Dari → Ke | Keterangan |
|---|-------|-----------|------------|
| 1 | `run.created` | `human:user` → `system:orchestrator` | Run dimulai dengan budget $1.00 |
| 2 | `task.created` (TASK-001) | `system:orchestrator` → `agent:ceo` | Task root, budget granted |
| 3 | `context.built` | `system:context` → `agent:ceo` | Hanya item relevan, ada yang di-drop |
| 4 | `policy.evaluated`, `model.selected`, `budget.reserved`, `model.call_started` | `system:*` | Token Guard lolos, tier `strong` |
| 5 | `model.call_completed`, `budget.settled` | `system:router` / `system:budget` | Usage tercatat |
| 6 | `task.delegate_requested` | `agent:ceo` → `system:orchestrator` | CEO meminta task riset |
| 7 | `task.created` (TASK-002), `task.assigned` | `system:orchestrator` → `agent:research` | Budget child $0.20 dari sisa $1.00 |
| 8 | `tool.call_requested` → `tool.call_completed` | `agent:research` ↔ `system:tool_runtime` | Pencarian web |
| 9 | `artifact.created` | `agent:research` → `topic:all` | `research.md` |
| 10 | `summary.created` | `system:summarizer` → `topic:all` | Ringkasan sekitar 800 token memakai model cheap |
| 11 | `task.completed` (TASK-002) | `agent:research` → `system:orchestrator` | Mengirim referensi, bukan isi penuh |
| 12 | (CTO mengikuti pola yang sama dengan langkah 6-11) | | |
| 13 | CEO sintesis, `task.completed` (TASK-001) | | |
| 14 | `run.stopped` (`success`) | `system:orchestrator` → `human:user` | Totals dilaporkan |

Payload lengkap untuk langkah-langkah penting:

**1. `run.created`**

<!-- example:run.created -->
```json
{
  "protocol_version": "societas/1",
  "schema_version": "1",
  "id": "evt_01J9ZBMN0V2JVCVJQ5HS63JFDS",
  "type": "run.created",
  "ts": "2026-10-06T09:00:00Z",
  "workspace_id": "ws_acme",
  "run_id": "RUN-001",
  "correlation_id": "cor_01J9ZBKGD7AHHWX216KWWYZH2T",
  "idempotency_key": "web-7f3a-001",
  "from": "human:user",
  "to": "system:orchestrator",
  "payload": {
    "goal": "Evaluasi apakah kita perlu menambahkan fitur baru.",
    "entry_agent": "ceo",
    "budget_request": { "max_total_tokens": 60000, "max_cost_usd": 1.00 }
  }
}
```

**2. `task.created` (task root untuk CEO)**

<!-- example:task.created -->
```json
{
  "protocol_version": "societas/1",
  "schema_version": "1",
  "id": "evt_01J9ZBJTD64PV176RGBNC6D0EC",
  "type": "task.created",
  "ts": "2026-10-06T09:00:01Z",
  "workspace_id": "ws_acme",
  "run_id": "RUN-001",
  "task_id": "TASK-001",
  "correlation_id": "cor_01J9ZBKGD7AHHWX216KWWYZH2T",
  "causation_id": "evt_01J9ZBMN0V2JVCVJQ5HS63JFDS",
  "from": "system:orchestrator",
  "to": "agent:ceo",
  "payload": {
    "task": {
      "id": "TASK-001",
      "run_id": "RUN-001",
      "parent_task_id": null,
      "title": "Evaluasi penambahan fitur baru",
      "goal": "Putuskan apakah fitur baru perlu ditambahkan, lengkap dengan alasan dan risiko.",
      "owner": "ceo",
      "created_by": "human:user",
      "priority": "high",
      "status": "ready",
      "dependencies": [],
      "deadline": null,
      "depth": 0,
      "attempt": 1,
      "expected_output": { "kind": "decision", "format": "markdown" },
      "budget": {
        "granted": {
          "max_total_tokens": 60000,
          "max_cost_usd": 1.00,
          "max_model_calls": 30,
          "max_child_tasks": 5,
          "max_depth": 4,
          "max_parallel_agents": 4,
          "max_agent_iterations": 8,
          "retry": { "max_attempts": 2, "max_total_retry_cost_usd": 0.10 }
        },
        "used": { "input_tokens": 0, "output_tokens": 0, "model_calls": 0, "tool_calls": 0, "estimated_cost_usd": 0 }
      },
      "created_at": "2026-10-06T09:00:01Z",
      "updated_at": "2026-10-06T09:00:01Z"
    }
  }
}
```

**3. `context.built`** (menunjukkan *mengapa* context tertentu diberikan, dan apa yang dibuang)

<!-- example:context.built -->
```json
{
  "protocol_version": "societas/1",
  "schema_version": "1",
  "id": "evt_01J9ZB8AXX885QPDR9R48STZ2S",
  "type": "context.built",
  "ts": "2026-10-06T09:00:02Z",
  "workspace_id": "ws_acme",
  "run_id": "RUN-001",
  "task_id": "TASK-001",
  "correlation_id": "cor_01J9ZBKGD7AHHWX216KWWYZH2T",
  "causation_id": "evt_01J9ZBJTD64PV176RGBNC6D0EC",
  "from": "system:context",
  "to": "agent:ceo",
  "payload": {
    "agent_id": "ceo",
    "token_budget": 12000,
    "tokens_used": 2250,
    "items": [
      { "kind": "system_prompt", "ref": "prompt:ceo", "tokens": 900, "reason": "wajib" },
      { "kind": "role", "ref": "role:ceo", "tokens": 250, "reason": "wajib" },
      { "kind": "task", "ref": "TASK-001", "tokens": 400, "reason": "task saat ini" },
      { "kind": "memory", "ref": "mem:arch-decision-transport", "tokens": 700, "reason": "keputusan transport sebelumnya relevan" }
    ],
    "dropped": [
      { "kind": "memory", "ref": "mem:finance-notes-2026q2", "reason": "low_relevance" }
    ]
  }
}
```

**5. `model.call_completed`**

<!-- example:model.call_completed -->
```json
{
  "protocol_version": "societas/1",
  "schema_version": "1",
  "id": "evt_01J9ZBC0AKZ3BBK8KA370CFV44",
  "type": "model.call_completed",
  "ts": "2026-10-06T09:00:08Z",
  "workspace_id": "ws_acme",
  "run_id": "RUN-001",
  "task_id": "TASK-001",
  "correlation_id": "cor_01J9ZBKGD7AHHWX216KWWYZH2T",
  "causation_id": "evt_01J9ZB8AXX885QPDR9R48STZ2S",
  "from": "system:router",
  "to": "agent:ceo",
  "payload": {
    "usage": {
      "model": "strong-model",
      "input_tokens": 2250,
      "output_tokens": 410,
      "duration_ms": 5120,
      "estimated_cost_usd": 0.031
    },
    "finish_reason": "stop",
    "confidence": 0.82
  }
}
```

**6. `task.delegate_requested`** (CEO meminta, tidak membuat task sendiri)

<!-- example:task.delegate_requested -->
```json
{
  "protocol_version": "societas/1",
  "schema_version": "1",
  "id": "evt_01J9ZB3G6A2NYNE5P9B4T3RTEA",
  "type": "task.delegate_requested",
  "ts": "2026-10-06T09:00:09Z",
  "workspace_id": "ws_acme",
  "run_id": "RUN-001",
  "task_id": "TASK-001",
  "correlation_id": "cor_01J9ZBKGD7AHHWX216KWWYZH2T",
  "causation_id": "evt_01J9ZBC0AKZ3BBK8KA370CFV44",
  "idempotency_key": "TASK-001-delegate-research-1",
  "from": "agent:ceo",
  "to": "system:orchestrator",
  "payload": {
    "title": "Riset gRPC vs REST untuk transport agent",
    "goal": "Bandingkan latency, reliability, dan kompleksitas implementasi gRPC vs REST. Berikan rekomendasi singkat dan sumber.",
    "rationale": "Keputusan butuh data pembanding terbaru. Memory CEO tidak memiliki benchmark.",
    "requested_assignee": "research",
    "expected_output": { "kind": "artifact", "format": "markdown" },
    "priority": "high",
    "complexity_hint": "medium",
    "context_hints": { "memory_queries": ["gRPC benchmark", "REST implementation"] },
    "budget_request": { "max_total_tokens": 12000, "max_cost_usd": 0.20 }
  }
}
```

**7. `task.created`** (Orchestrator memberi budget; di sini $0.20 dari sisa $0.969 milik parent)

<!-- example:task.created -->
```json
{
  "protocol_version": "societas/1",
  "schema_version": "1",
  "id": "evt_01J9ZBHB2DZKSXQ0S74ER1KKPW",
  "type": "task.created",
  "ts": "2026-10-06T09:00:10Z",
  "workspace_id": "ws_acme",
  "run_id": "RUN-001",
  "task_id": "TASK-002",
  "correlation_id": "cor_01J9ZBKGD7AHHWX216KWWYZH2T",
  "causation_id": "evt_01J9ZB3G6A2NYNE5P9B4T3RTEA",
  "from": "system:orchestrator",
  "to": "agent:research",
  "payload": {
    "task": {
      "id": "TASK-002",
      "run_id": "RUN-001",
      "parent_task_id": "TASK-001",
      "title": "Riset gRPC vs REST untuk transport agent",
      "goal": "Bandingkan latency, reliability, dan kompleksitas implementasi gRPC vs REST. Berikan rekomendasi singkat dan sumber.",
      "owner": "research",
      "created_by": "agent:ceo",
      "priority": "high",
      "status": "ready",
      "dependencies": [],
      "deadline": null,
      "depth": 1,
      "attempt": 1,
      "expected_output": { "kind": "artifact", "format": "markdown" },
      "budget": {
        "granted": {
          "max_total_tokens": 12000,
          "max_cost_usd": 0.20,
          "max_model_calls": 10,
          "max_tool_calls": 20,
          "max_time_seconds": 300
        },
        "used": { "input_tokens": 0, "output_tokens": 0, "model_calls": 0, "tool_calls": 0, "estimated_cost_usd": 0 }
      },
      "created_at": "2026-10-06T09:00:10Z",
      "updated_at": "2026-10-06T09:00:10Z"
    }
  }
}
```

**8. Tool call**

<!-- example:tool.call_requested -->
```json
{
  "protocol_version": "societas/1",
  "schema_version": "1",
  "id": "evt_01J9ZB0P08MESD27WWF0X2GTAX",
  "type": "tool.call_requested",
  "ts": "2026-10-06T09:00:20Z",
  "workspace_id": "ws_acme",
  "run_id": "RUN-001",
  "task_id": "TASK-002",
  "correlation_id": "cor_01J9ZBKGD7AHHWX216KWWYZH2T",
  "causation_id": "evt_01J9ZBHB2DZKSXQ0S74ER1KKPW",
  "from": "agent:research",
  "to": "system:tool_runtime",
  "payload": {
    "tool_call_id": "tc_01J9ZBGP79PCNF7AHK55JHQBKY",
    "tool": "web.search",
    "arguments": { "query": "gRPC vs REST latency benchmark" },
    "timeout_ms": 20000
  }
}
```

<!-- example:tool.call_completed -->
```json
{
  "protocol_version": "societas/1",
  "schema_version": "1",
  "id": "evt_01J9ZBJ658J92SADYG3P19CST8",
  "type": "tool.call_completed",
  "ts": "2026-10-06T09:00:22Z",
  "workspace_id": "ws_acme",
  "run_id": "RUN-001",
  "task_id": "TASK-002",
  "correlation_id": "cor_01J9ZBKGD7AHHWX216KWWYZH2T",
  "causation_id": "evt_01J9ZB0P08MESD27WWF0X2GTAX",
  "from": "system:tool_runtime",
  "to": "agent:research",
  "payload": {
    "tool_call_id": "tc_01J9ZBGP79PCNF7AHK55JHQBKY",
    "status": "ok",
    "output": "8 hasil ditemukan.",
    "truncated": false,
    "duration_ms": 1840
  }
}
```

**9-10. Artifact dan summary** (yang dikirim ke agent lain adalah summary + referensi)

<!-- example:artifact.created -->
```json
{
  "protocol_version": "societas/1",
  "schema_version": "1",
  "id": "evt_01J9ZBMWFA97DP1VJ770C2Y52A",
  "type": "artifact.created",
  "ts": "2026-10-06T09:01:30Z",
  "workspace_id": "ws_acme",
  "run_id": "RUN-001",
  "task_id": "TASK-002",
  "correlation_id": "cor_01J9ZBKGD7AHHWX216KWWYZH2T",
  "causation_id": "evt_01J9ZBJ658J92SADYG3P19CST8",
  "from": "agent:research",
  "to": "topic:all",
  "payload": {
    "artifact": {
      "id": "art_01J9ZB97J90P9MH8TKCE9C9KF3",
      "name": "research.md",
      "kind": "markdown",
      "path": "artifacts/RUN-001/TASK-002/research.md",
      "checksum": "sha256:66f62d1807d3821a3865f2573b69c74be033f1341240ac861fefc6d430bff5e0",
      "size_bytes": 18420,
      "version": 1,
      "task_id": "TASK-002",
      "created_by": "agent:research",
      "created_at": "2026-10-06T09:01:30Z"
    }
  }
}
```

<!-- example:summary.created -->
```json
{
  "protocol_version": "societas/1",
  "schema_version": "1",
  "id": "evt_01J9ZBMB07Y7X7H238CJYHN9V9",
  "type": "summary.created",
  "ts": "2026-10-06T09:01:34Z",
  "workspace_id": "ws_acme",
  "run_id": "RUN-001",
  "task_id": "TASK-002",
  "correlation_id": "cor_01J9ZBKGD7AHHWX216KWWYZH2T",
  "causation_id": "evt_01J9ZBMWFA97DP1VJ770C2Y52A",
  "from": "system:summarizer",
  "to": "topic:all",
  "payload": {
    "summary": {
      "id": "sum_01J9ZB75QCACYADGWFKD86P7W1",
      "artifact_id": "art_01J9ZB97J90P9MH8TKCE9C9KF3",
      "artifact_version": 1,
      "token_estimate": 780,
      "generated_by": "system:summarizer",
      "model": "cheap-model",
      "body": {
        "text": "gRPC unggul pada performa dan type-safety. REST lebih sederhana dan lebih matang tooling-nya.",
        "findings": ["gRPC mengurangi latency pada high-throughput calls", "REST cukup untuk mode lokal"],
        "risks": ["Kompleksitas implementasi gRPC lebih tinggi"],
        "recommendation": "Mulai dengan HTTP/REST. Evaluasi gRPC ketika throughput menjadi bottleneck.",
        "sources": ["research.md#benchmark", "research.md#risiko"]
      }
    }
  }
}
```

**11. `task.completed`**

<!-- example:task.completed -->
```json
{
  "protocol_version": "societas/1",
  "schema_version": "1",
  "id": "evt_01J9ZB8MHE3A7GDTXS0TWR5FQ3",
  "type": "task.completed",
  "ts": "2026-10-06T09:01:40Z",
  "workspace_id": "ws_acme",
  "run_id": "RUN-001",
  "task_id": "TASK-002",
  "correlation_id": "cor_01J9ZBKGD7AHHWX216KWWYZH2T",
  "causation_id": "evt_01J9ZBMWFA97DP1VJ770C2Y52A",
  "from": "agent:research",
  "to": "system:orchestrator",
  "payload": {
    "result_status": "success",
    "artifact_ids": ["art_01J9ZB97J90P9MH8TKCE9C9KF3"],
    "summary_ids": ["sum_01J9ZB75QCACYADGWFKD86P7W1"],
    "usage": {
      "input_tokens": 9120,
      "output_tokens": 2240,
      "model_calls": 3,
      "tool_calls": 2,
      "estimated_cost_usd": 0.087
    }
  }
}
```

**Contoh penolakan: fan-out melebihi batas** (I12)

<!-- example:task.delegate_rejected -->
```json
{
  "protocol_version": "societas/1",
  "schema_version": "1",
  "id": "evt_01J9ZB2SAX2698XVPBEKQRRRP6",
  "type": "task.delegate_rejected",
  "ts": "2026-10-06T09:05:00Z",
  "workspace_id": "ws_acme",
  "run_id": "RUN-001",
  "task_id": "TASK-001",
  "correlation_id": "cor_01J9ZBKGD7AHHWX216KWWYZH2T",
  "causation_id": "evt_01J9ZBD8Y6K6M8JYG02EPDVJ2G",
  "from": "system:orchestrator",
  "to": "agent:ceo",
  "payload": {
    "request_event_id": "evt_01J9ZBD8Y6K6M8JYG02EPDVJ2G",
    "error": {
      "code": "FANOUT_LIMIT_EXCEEDED",
      "category": "LIMIT_ERROR",
      "message": "TASK-001 sudah memiliki 5 child task aktif (batas 5). Gabungkan pekerjaan atau tunggu salah satu selesai.",
      "retryable": false,
      "details": { "max_child_tasks": 5, "current_children": 5 }
    }
  }
}
```

**Contoh eskalasi budget** (5A.20, I14)

<!-- example:budget.exceeded -->
```json
{
  "protocol_version": "societas/1",
  "schema_version": "1",
  "id": "evt_01J9ZBS1VHX1W4W4AGPX1QYFDC",
  "type": "budget.exceeded",
  "ts": "2026-10-06T09:20:00Z",
  "workspace_id": "ws_acme",
  "run_id": "RUN-001",
  "correlation_id": "cor_01J9ZBKGD7AHHWX216KWWYZH2T",
  "causation_id": "evt_01J9ZBC0AKZ3BBK8KA370CFV44",
  "from": "system:budget",
  "to": "system:orchestrator",
  "payload": {
    "scope": "run",
    "scope_id": "RUN-001",
    "limit": "max_cost_usd",
    "error": {
      "code": "BUDGET_EXCEEDED",
      "category": "BUDGET_ERROR",
      "message": "Budget biaya run RUN-001 tercapai.",
      "retryable": false,
      "details": { "scope": "run", "used": 1.0, "limit": 1.0 }
    }
  }
}
```

<!-- example:approval.requested -->
```json
{
  "protocol_version": "societas/1",
  "schema_version": "1",
  "id": "evt_01J9ZB9Y4S06VP158SP5K84RF1",
  "type": "approval.requested",
  "ts": "2026-10-06T09:20:01Z",
  "workspace_id": "ws_acme",
  "run_id": "RUN-001",
  "correlation_id": "cor_01J9ZBKGD7AHHWX216KWWYZH2T",
  "causation_id": "evt_01J9ZBS1VHX1W4W4AGPX1QYFDC",
  "from": "system:policy",
  "to": "human:user",
  "payload": {
    "approval_id": "apr_01J9ZB6W9B4V3CGZKBZ01PDVKN",
    "action": "budget.increase:run",
    "reason": "Run RUN-001 mencapai budget $1.00 sebelum review selesai. Perlu tambahan untuk melanjutkan.",
    "trigger": "budget",
    "risk": "low",
    "details": { "suggested_increase_usd": 0.30 }
  }
}
```

## 72A.12 Validasi, Versioning & Kompatibilitas

**Validasi di dua titik:** saat pengirim mempublikasikan, dan saat Event Bus menerima. Pesan yang gagal validasi **tidak masuk Event Store**. Pesan itu dicatat di dead-letter log beserta alasannya, dan pengirim menerima `SCHEMA_VALIDATION_FAILED`.

**Versioning:**

- `schema_version` menunjukkan versi seluruh set schema di Section 72A.
- Karena schema bersifat strict (`additionalProperties: false`), setiap perubahan bentuk (termasuk menambah field opsional) menaikkan `schema_version`.
- Konsumen wajib mendukung versi terbaru (N) dan sebelumnya (N-1). Perubahan breaking harus disertai fungsi migrasi (#72).
- Event Store menyimpan event apa adanya beserta `schema_version`, sehingga replay (#68) menjalankan migrasi saat membaca.
- Sebelum "Stable agent schema" tercapai (#82), schema boleh berubah in-place. Setelah itu aturan di atas berlaku penuh.

**Tata letak repo yang disarankan:**

```text
schemas/
  1/
    common.json
    envelope.json
    budget.json  usage.json  usage_totals.json  error.json
    task.json  artifact_ref.json  summary.json
    payloads/
      run_created.json  delegate_requested.json  ...
    registry.json        # type -> schema, dari tabel 72A.7
```

`societas doctor` (#94) sebaiknya memeriksa bahwa file schema lengkap dan registry konsisten.

## 72A.13 Contract Acceptance Criteria

Kontrak dianggap selesai jika:

- Semua contoh JSON di Section 72A lolos validasi terhadap schema (dijalankan di CI)
- Setiap `type` di registry punya tepat satu schema, dan tidak ada schema yatim
- Envelope tanpa field wajib ditolak
- `type` yang tidak dikenal ditolak
- Payload dengan field tambahan ditolak
- `idempotency_key` ganda tidak menimbulkan efek ganda
- Grant budget anak yang melebihi sisa parent ditolak dengan `BUDGET_EXCEEDED`
- Delegasi melebihi `max_child_tasks` ditolak dengan `FANOUT_LIMIT_EXCEEDED`
- Transisi task di luar tabel 72A.6 ditolak
- Urutan event model call sesuai 72A.10, dan model tidak dipanggil jika guard gagal
- Tidak ada jalur agent-ke-agent yang melewati Event Bus
- Konten melebihi batas inline ditolak atau dipindahkan menjadi artifact
- Replay dari Event Store menghasilkan state task yang sama

---

# 79. MVP

MVP harus kecil.

Target MVP:

```text
User
 ↓
CEO
 ├── Research
 └── CTO
       ↓
     Engineer
```

Capabilities:

- agent config
- agent runtime
- task creation
- delegation
- messaging
- event stream
- artifact creation
- basic memory
- tool execution
- human approval
- basic dashboard
- Event Bus internal (Go channel)
- orchestrator
- budget manager
- context manager
- model router
- cost tracking
- basic policy engine

---

# 80. MVP Demo

User menjalankan:

```bash
societas init my-company
cd my-company
societas serve
```

Kemudian:

```bash
societas start
```

Dashboard:

```text
SOCIETAS

CEO        ● Working
CTO        ● Working
Research   ● Working
Engineer   ○ Idle
```

User:

```text
CEO:
"Research apakah event-driven architecture
cocok untuk multi-agent system."
```

CEO:

```text
Assigning:

Research -> technology research
CTO      -> architecture evaluation
```

Research berjalan.

CTO berjalan paralel.

CEO menggabungkan hasil.

Kemudian:

```text
CEO:
"Engineer, build a minimal prototype."
```

Engineer membuat:

```text
prototype/
benchmark/
report.md
```

Reviewer mengecek.

User mendapat hasil akhir.

---

# 81. MVP Acceptance Criteria

MVP dianggap selesai jika:

### Agents

- minimal 4 agent dapat berjalan
- role dapat dikonfigurasi
- model dapat dikonfigurasi
- status agent terlihat

### Tasks

- task dapat dibuat
- task dapat didelegasikan
- dependency dapat digunakan
- task dapat selesai/gagal

### Communication

- agent dapat saling mengirim message
- message dapat di-stream
- event dapat dipantau

### Tools

- minimal filesystem
- shell terbatas
- git opsional

### Artifacts

- agent dapat membuat artifact
- artifact dapat dibaca agent lain

### Human

- user dapat memberikan task
- user dapat approve/reject action

### Transport

- agent dapat berkomunikasi melalui Event Bus internal
- reconnect dasar tersedia
- event tidak hilang secara tidak terkendali

### AI Control Plane

- budget task enforced
- context budget enforced
- model selection tersedia
- token/cost usage tercatat
- maximum iterations tersedia
- fan-out limit tersedia
- stop condition tersedia

### Contracts

- semua event memakai envelope Section 72A.3
- payload divalidasi terhadap schema (boundary publish dan receive)
- type dan field tidak dikenal ditolak
- agent tidak dapat berkomunikasi langsung, semua lewat Event Bus
- transisi status task mengikuti 72A.6
- error memakai katalog 72A.9

### Dashboard

- agent status
- task status
- live events
- artifacts
- approvals

---

# 82. Phase Roadmap

## v0.1 — Foundation

- Workspace
- Agent config
- Agent runtime
- Local model/provider interface
- Task model
- Event model
- SQLite
- Web API (backend)

---

## v0.2 — Multi-Agent

- Multiple agents
- Delegation
- Agent messaging
- Task graph
- Artifact system
- Basic memory

---

## v0.3 — Real-Time Layer

- Event Bus (Go channel)
- Streaming message
- Event subscriptions
- Agent presence
- Reconnect
- Heartbeat
- Backpressure

---

## v0.4 — Agent Company

- CEO orchestrator
- Role system
- Parallel task execution
- Approval system
- Tool permissions
- Run history
- Replay

---

## v0.5 — Developer Agent

- Filesystem
- Shell
- Git
- Test execution
- Code artifacts
- Review agent
- Research agent

---

## v0.6 — Live Workspace

- Full dashboard
- Agent graph
- Task board
- Live event stream
- Artifact explorer
- Approval center
- Usage analytics

---

## v0.7 — Multimodal

- Voice
- ASR
- TTS
- Image inputs
- Streaming audio
- Real-time interruption

---

## v0.8 — Distributed

- Remote agents
- WebSocket relay
- Multi-machine
- Multi-hop
- Shared state
- Node discovery

---

## v0.9 — Advanced Agent Runtime

- Advanced memory
- Context management
- Agent-to-agent protocols
- More tools
- Advanced scheduling
- Retry policies
- Cost optimization

---

## v1.0 — Stable Platform

- Stable protocol
- Stable agent schema
- Stable task schema
- Migration tools
- Documentation
- Test suite
- Security review
- Performance benchmarks

---

# 83. Future Experimental Ideas

Eksperimen dapat dilakukan tanpa mengubah core product.

## 83.1 Voice Company

User berbicara dengan CEO.

CEO dapat memanggil CTO/Research/Engineer.

---

## 83.2 AI War Room

Beberapa agent berdebat mengenai satu keputusan.

Contoh:

```text
CEO:
Should we use gRPC or REST?

CTO:
gRPC.

Security:
WebSocket is simpler for deployment.

Performance:
gRPC wins under concurrency.

CEO:
Reviewer, resolve this.
```

---

## 83.3 AI Standup

Setiap hari:

```text
CEO:
Give me status.

CTO:
3 tasks done.

Research:
2 findings.

Engineer:
PR ready.

Reviewer:
1 blocker.
```

System menghasilkan:

```text
daily-standup.md
```

---

## 83.4 AI Board Meeting

Semua role ikut rapat virtual:

```text
CEO
CTO
CPO
Research
Security
Finance
```

Agenda → discussion → decision → artifacts.

---

## 83.5 Agent Simulation

User dapat menjalankan organisasi tanpa manusia sebagai test.

```text
autonomous run
```

Dengan budget:

```text
max_tokens
max_time
max_tasks
max_cost
```

---

## 83.6 Agent Market

Future, bukan MVP.

User dapat membuat/import role pack:

```text
security-team
startup-team
game-dev-team
research-team
```

---

# 85. Technical Priorities

Urutan engineering:

```text
1. Correctness
2. Agent lifecycle
3. Task correctness
4. Tool safety
5. Event consistency
6. Reliability
7. Real-time transport
8. Observability
9. Performance
10. UX
11. Distributed execution
```

---

# 86. Go Strategy

Go digunakan untuk seluruh backend:

- agent runtime (goroutine per agent)
- event bus (channel)
- HTTP API server
- WebSocket server
- concurrency
- storage layer

Kelebihan yang ingin dicapai:

- development speed tinggi
- concurrency model simpel (goroutine + channel)
- single binary deployment
- compile cepat
- standard library kuat (net/http, encoding/json)

---

# 89. Security Checklist

Sebelum release production:

```text
[ ] Secret redaction
[ ] Tool permissions
[ ] Shell restrictions
[ ] Path restrictions
[ ] Approval system
[ ] Authenticated agent session
[ ] Transport security
[ ] Input validation
[ ] Resource limits
[ ] Safe logging
[ ] Artifact isolation
[ ] Workspace isolation
```

---

# 90. Data Ownership

Default:

```text
User owns:
- workspace
- events
- artifacts
- memory
- credentials
- configuration
```

Tidak ada telemetry external secara default kecuali user memilihnya.

---

# 94. Web Health Check

Endpoint untuk debugging dan monitoring:

```text
GET /health
GET /health/agents
GET /health/event-bus
GET /health/storage
GET /health/providers
```

Response:

```json
{
  "status": "ok",
  "workspace": "tunly",
  "agents": { "running": 4, "idle": 1 },
  "event_bus": "connected",
  "storage": "ok",
  "providers": { "openai": "ok" }
}
```

---

# 97. Definition of Done

Feature dianggap selesai jika:

## Code

- implementation selesai
- error handling tersedia
- tidak ada unsafe default yang tidak diperlukan

## Tests

- unit test
- integration test bila relevan
- failure test bila relevan

## Security

- permission diperiksa
- secret tidak bocor
- input divalidasi
- resource bounded

## Documentation

- config documented
- API documented
- protocol documented
- examples tersedia

## Observability

- logs tersedia
- events dapat dilacak
- correlation ID tersedia bila relevan

---

# 99. First Killer Demo

Demo pertama harus sederhana tetapi terasa hidup:

```text
User
 |
 v
CEO
 |
 +----> Research
 |
 +----> CTO
 |
 +----> Security
          |
          v
        CEO
          |
          v
       Engineer
          |
          v
       Reviewer
          |
          v
        Human
```

Semua aktivitas tampil real-time.

Dashboard menampilkan:

```text
CEO        ● Delegating
Research   ● Researching
CTO        ● Reviewing
Security   ● Analyzing
Engineer   ● Waiting
Reviewer   ○ Idle
```

Live event stream:

```text
CEO -> Research:
"Investigate best practices for multi-agent systems."

Research:
"Starting research."

CEO -> CTO:
"Evaluate transport architecture."

CTO:
"Working on architecture."

Research -> CEO:
"Found 8 relevant findings."

CEO -> Engineer:
"Build minimal prototype."

Engineer:
"Starting implementation."
```

Ketika semuanya selesai:

```text
Decision:
Proceed with Event Bus + WebSocket for real-time communication.

Artifacts:
research.md
architecture.md
security-review.md
benchmark.md
prototype/
```

Human tinggal memutuskan.

---

# 101. Final Product Vision

Tujuan akhirnya bukan membuat:

```text
chatbot #9999
```

Tetapi membuat:

```text
                     YOU
                      |
                      v
                 SOCIETAS
                      |
       +--------------+--------------+
       |              |              |
      CEO            CTO           Research
       |              |              |
       +--------------+--------------+
                      |
                 Agent Network
                      |
       +--------------+--------------+
       |              |              |
     Engineer      Reviewer       Security
       |              |              |
       +--------------+--------------+
                      |
                   ARTIFACTS
                      |
                      v
                     YOU
```

Sistem harus terasa seperti sebuah **organisasi hidup**:

- agent punya role
- agent punya tanggung jawab
- agent punya state
- agent dapat bekerja paralel
- agent dapat berkomunikasi realtime
- agent dapat memakai tools
- agent dapat membuat artifacts
- agent dapat mereview pekerjaan
- agent dapat meminta approval
- manusia tetap memegang keputusan penting

Event Bus menjadi lapisan komunikasi real-time yang memungkinkan organisasi tersebut berjalan sebagai sistem yang terkoordinasi.

---

# 102. Core Philosophy

```text
Build for yourself first.

Make it useful before making it popular.

Make it simple before making it distributed.

Make it reliable before making it autonomous.

Make it observable before making it complex.

Make it fast, then prove it with benchmarks.

Keep the core open.

Let the agents do the work.

Keep the human in control.
```

---

# 103. Immediate Development Order

Urutan pertama yang direkomendasikan:

```text
1. Workspace
2. Agent schema
3. Agent runtime
4. LLM provider abstraction
5. Task model
6. Event model
7. Contracts (schema + validator, Section 72A)
8. SQLite storage
9. Orchestrator
10. Budget Manager
11. Context Manager
12. Model Router
13. Cost Tracker
14. Policy Engine
15. Agent messaging
16. CEO delegation
17. Artifact system
18. Tool runtime
19. Permission system
20. Approval system
21. Event Bus (Go channel)
22. Streaming
23. Reconnect / heartbeat
24. Dashboard
25. Research agent
26. Engineer agent
27. Reviewer agent
28. Memory
29. Usage optimization
30. Voice / multimodal
31. Distributed agents
```

---

# 104. Absolute MVP Scope

MVP wajib bisa melakukan satu flow end-to-end:

```text
Human
  |
  v
CEO
  |
  +------> Research
  |
  +------> CTO
              |
              v
           Engineer
              |
              v
           Reviewer
              |
              v
             CEO
              |
              v
            Human
```

Dengan:

```text
- Task
- Delegation
- Agent-to-agent message
- Tool call
- Artifact
- Event stream
- Human approval
- Basic dashboard
- Budget & context control (AI Control Plane)
- Contracts tervalidasi (envelope + schema, Section 72A)
```

Jika flow ini sudah bekerja dengan stabil, project sudah mempunyai dasar produk yang kuat.

---

# 105. Anti-Boncos Rules

Aturan default untuk menjaga biaya LLM:

1. Jangan broadcast full context ke semua agent.
2. Gunakan summary + artifact reference.
3. Gunakan model murah untuk routing dan summarization.
4. Gunakan model kuat hanya ketika dibutuhkan.
5. Semua task memiliki token/cost budget.
6. Semua retry memiliki batas.
7. Semua autonomous loop memiliki batas iterasi.
8. Semua fan-out memiliki batas.
9. Context retrieval harus relevance-based.
10. Model call harus melewati Budget Manager sebelum dieksekusi.

Prinsip paling penting:

> Token adalah resource. Treat token seperti CPU, RAM, bandwidth, dan waktu.

Jika sebuah workflow tidak dapat menjelaskan mengapa sebuah agent dipanggil dan mengapa context tertentu diberikan, workflow tersebut harus dianggap belum optimal.

Setiap delegasi wajib mencatat `rationale` (mengapa agent ini dipanggil), dan setiap context yang dibangun wajib mencatat `reason` per item (mengapa context ini diberikan). Lihat Section 72A.8.
