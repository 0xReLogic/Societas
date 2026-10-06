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

State agent menggambarkan aktivitas dan berbeda dari enum status task. Task yang menunggu approval dapat diparkir, sementara agennya kembali `idle` atau mengambil task independen lain (#40.1); state task kanonik tetap mengikuti 72A.6.

---

# 7. Task System

Task adalah unit pekerjaan. Task tidak langsung dieksekusi dari prompt mentah user — ia melewati **Intake Pipeline berjenjang** (lihat #7.1) sebelum mencapai Worker Agent.

Untuk onboarding, pahami dulu task sebagai unit ber-goal, owner, status, dependency, budget, dan output. Lompat ke #8 untuk melihat hubungan antar-task; detail mesin intake #7.1 dapat dibaca setelah #5A.

## 7.1 Intake & Routing Pipeline

Instruksi user diproses berjenjang sebelum task dieksekusi. Bagian ini menjelaskan routing yang disebut di #5A.1 dan dapat dibaca setelah model control plane dipahami:

### 1. Intake Layer (Front-Office Sanitizer)

- LLM generatif murah dan cepat (Flash tier) membaca prompt mentah user — termasuk typo dan bahasa santai — plus file dokumentasi `PROJECT_MAP.md` (pemetaan fungsi direktori 1 halaman).
- Menghasilkan brief task terstruktur: `goal`, `target_modules`, `risk_hint`.
- Fleksibel: jika folder/fitur belum terpetakan, fallback otomatis ke `target_path: null` dan `risk_hint: "normal"`.

**Maintenance `PROJECT_MAP.md` (anti-basi):** file ini **tidak boleh di-update manual** — akan basi dalam hitungan minggu dan Intake mulai salah nebak target modul. `PROJECT_MAP.md` digenerate ulang secara deterministik oleh backend Go (struktur direktori via `tree -d -L 3` + deskripsi singkat per modul) **setiap kali ada task yang berhasil di-merge ke `main`** (lihat #60.4). Generator ini berjalan sebagai task background 0 token — bukan LLM call.

Untuk final-candidate approval (I17/I19, 72A.10), jalankan generator **sesudah rebase dan sebelum freeze, build gate, Semantic Rebase, atau review** agar perubahan map ikut candidate tree yang benar-benar diuji. Semantic evidence mengikat versi map dalam candidate. Setelah merge receipt terkonfirmasi, regenerasi otomatis harus menghasilkan konten identik; perbedaan masuk task perbaikan dengan rebase, gate, Semantic Rebase, review, dan approval baru, bukan commit diam-diam ke `main`. Format/sumber deskripsi per modul tetap keputusan terpisah dan wajib menjadi input candidate bila memengaruhi hasil intake.

### 2. Cognitive Router (Jev AI — System 1 Decision Engine)

Berada di dalam Control Plane, menjawab keputusan rute cepat (latensi 70–500ms) dengan format primitif non-chat:

- `Choice` -> `assignee` agen yang tepat
- `Choice` -> model tier worker (`cheap` | `medium` | `thinking`)
- `Score` / `Choice` -> skor evaluasi risiko task

`thinking` adalah label tampilan, dipetakan adapter menjadi wire tier `strong`. Nilai kanonik yang dipersist/dikirim tetap `cheap | medium | strong` (72A.4); jangan mengirim literal `thinking`.

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

Task membentuk **DAG** (directed acyclic graph): node adalah task, edge adalah dependency, dan siklus tidak diperbolehkan. Task yang tidak saling bergantung dapat berjalan paralel; task yang menunggu dependency baru siap setelah pendahulunya menghasilkan output.

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

Sesudah memahami lifecycle dan DAG, lanjutkan ke [§5A AI Control Plane](02-ai-control-plane.md): mesin yang menjadwalkan task/agen dan mengontrol token, biaya, model, serta context. Setelah itu kembali ke #7.1 untuk intake dan #9 untuk delegation.

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
