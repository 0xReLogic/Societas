<!-- Doc 03 — Lifecycle, Task, Graph, Delegation (§6–9)
     Bagian dari societas-full-product-spec. Urutan dokumen diatur di README.md.
     Nomor section dipertahankan; referensi silang antar-doc memakai nomor section (#N, 5A.x, 72A.x). -->

# 6. Agent Lifecycle

Setiap agent memiliki lifecycle:

```text
created
   |
   v
idle
   |
   v
working
   |
   +------> waiting
   |
   +------> blocked
   |
   +------> approval_required
   |
   v
completed
   |
   v
idle
```

Status agent harus terlihat pada dashboard.

---

# 7. Task System

Task adalah unit pekerjaan. Task tidak langsung dieksekusi dari prompt mentah user — ia melewati **Intake Pipeline berjenjang** (lihat #7.1) sebelum mencapai Worker Agent.

## 7.1 Intake & Routing Pipeline

Instruksi user diproses berjenjang sebelum task dieksekusi:

### 1. Intake Layer (Front-Office Sanitizer)

- LLM generatif murah dan cepat (Flash tier) membaca prompt mentah user — termasuk typo dan bahasa santai — plus file dokumentasi `PROJECT_MAP.md` (pemetaan fungsi direktori 1 halaman).
- Menghasilkan brief task terstruktur: `goal`, `target_modules`, `risk_hint`.
- Fleksibel: jika folder/fitur belum terpetakan, fallback otomatis ke `target_path: null` dan `risk_hint: "normal"`.

### 2. Cognitive Router (Jev AI — System 1 Decision Engine)

Berada di dalam Control Plane, menjawab keputusan rute cepat (latensi 70–500ms) dengan format primitif non-chat:

- `Choice` -> `assignee` agen yang tepat
- `Choice` -> model tier worker (`cheap` | `medium` | `thinking`)
- `Score` / `Choice` -> skor evaluasi risiko task

### 3. Control Plane / Go Runtime (Deterministic Enforcer)

Menjalankan state machine (72A.6), menghitung budget saldo token, mengunci sandbox disk OS (Path Jailing #22.2), dan memproses event tombol UI (#33.3) — semua tanpa token LLM.

```text
User prompt mentah
      |
      v
Intake (Flash tier) -> brief { goal, target_modules, risk_hint }
      |
      v
Jev AI (Choice/Score) -> assignee + model tier + risk
      |
      v
Go Runtime -> create task -> worker agent
```

Contoh:

```yaml
id: TASK-001
title: Research gRPC transport
owner: research
created_by: ceo
priority: high
status: pending
```

Task memiliki:

- ID
- parent task
- owner
- creator
- description
- priority
- status
- dependencies
- deadline
- artifacts
- events
- cost/usage metadata

Bentuk lengkap task (field, tipe, dan state machine) ada di **Section 72A.5 dan 72A.6**. Contoh di atas disederhanakan.

---

# 8. Task Graph

Task dapat membentuk graph.

Contoh:

```text
TASK-001
Research transport options
    |
    +---- TASK-002
    |     Compare protocols
    |
    +---- TASK-003
          Analyze architecture
              |
              v
          TASK-004
          CTO Review
              |
              v
          TASK-005
          Engineering POC
```

Task dapat berjalan:

- sequential
- parallel
- conditional

---

# 9. Delegation

CEO atau agent tertentu dapat mendelegasikan task.

Contoh:

```text
CEO:
"Investigate whether gRPC is suitable
for real-time agent communication."
```

CEO membuat:

```text
TASK-101 -> Research
TASK-102 -> CTO
TASK-103 -> Security
```

Setelah selesai:

```text
Research  ──┐
CTO        ──┼──> CEO
Security   ──┘
```

CEO kemudian membuat keputusan.

---
