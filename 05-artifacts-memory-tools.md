<!-- Doc 05 — Artifact, Memory, Tools (§17–21)
     Bagian dari societas-full-product-spec. Urutan dokumen diatur di README.md.
     Nomor section dipertahankan; referensi silang antar-doc memakai nomor section (#N, 5A.x, 72A.x). -->

# 17. Artifact System

Output agent tidak boleh hanya dianggap sebagai text response.

Artifact adalah output yang dapat dipakai agent lain.

Contoh:

```text
research.md
architecture.md
benchmark.json
diagram.svg
decision.md
patch.diff
pull-request.md
test-report.md
```

## 17.1 Contract-First Integration (Generate-First, Gate-Second, Prompt-Last)

Agen dilarang menulis fungsi fetch/call Web3 atau API dari nol secara manual. Alur serah terima backend/smart contract ke frontend:

1. **Pinning Kontrak:** task frontend wajib mengunci `contract_hash` (SHA256 dari OpenAPI spec / Contract ABI). Jika spec berubah, task ditandai **stale**.
2. **Codegen Otomatis:** Go runtime men-generate client TypeScript/Rust binding via CLI tool (`orval`, `wagmi` typegen, `viem`) sebelum agen bekerja.
3. **Strict Usage:** agen hanya boleh mengimpor dan memanggil fungsi hasil generate tersebut.
4. **Token-Saver Lookup:** agen tidak menerima seluruh spec OpenAPI/ABI ke prompt. Disediakan tool deterministik `contract.lookup(operation_id)` yang mengembalikan potongan spec relevan saja — tanpa vector search.

Artifact memiliki:

- ID
- owner
- creator
- task
- type
- path
- checksum
- created_at
- updated_at
- metadata

---

# 18. Artifact Flow

```text
Research Agent
      |
      v
research.md
      |
      v
CEO
      |
      v
architecture task
      |
      v
CTO
      |
      v
architecture.md
      |
      v
Engineer
      |
      v
code + tests
      |
      v
Reviewer
      |
      v
review.md
```

---

# 19. Memory System

Memory dibagi menjadi beberapa level dan disimpan sesuai sifatnya pada dua pilar penyimpanan (Dual-Storage Architecture, lihat #37):

- Data terstruktur/operasional (task state, run history, approval, akumulasi budget) -> **Operational Store** (SQLite)
- Representasi semantik (embedding artifact, ringkasan riset, koordinat memori masa lalu) -> **Cognitive Store** (Embedded Vector DB)

## 19.1 Agent Memory

Informasi khusus agent.

Contoh:

```text
CTO preferences
Engineering decisions
Technical context
Past reviews
```

## 19.2 Workspace Memory

Informasi seluruh organisasi.

Contoh:

```text
Architecture decisions
Project direction
Company rules
Important findings
```

## 19.3 Task Memory

Context yang hanya relevan terhadap satu task.

## 19.4 Run Memory

Context selama satu execution.

## 19.5 Memory Storage Mapping

Setiap level memory di atas di-map ke pilar penyimpanan:

- Agent Memory & Workspace Memory: entry terstruktur (sumber, timestamp, scope) di SQLite; isi naratifnya di-embed ke Vector DB agar dapat di-retrieve semantik.
- Task Memory: relasi task -> artifact/memory disimpan di SQLite; ringkasannya di-embed untuk retrieval.
- Run Memory: append-only di event log SQLite; tidak di-embed (ephemeral).

Retrieval semantik selalu melewati Vector DB dan mengembalikan ID referensi (5A.24) — bukan pencarian teks mentah di SQLite.

## 19.6 Memory Curation (Anti Semantic Drift / Zombie Memory)

Vector DB bekerja berdasarkan kemiripan teks (cosine similarity), **bukan status kebenaran atau recency**. Ia tidak tahu dokumen mana yang sudah basi — `architecture_v1.md` (nullifier 2 status) dan `nullifier_v2.md` (4 status) bisa sama-sama ter-retrieve karena kemiripannya hampir sama, sehingga agen menerima dua fakta kontradiktif dan bisa "ketularan" keputusan lama yang sudah dibatalkan. Semakin tua proyek, makin banyak zombie memory: keputusan dibatalkan, bug log yang sudah di-patch, nama fungsi yang sudah deprecated.

Empat aturan kurasi deterministik di Go + SQLite — tanpa algoritma AI tambahan:

1. **Filter pintu masuk — jangan embed semua hal.** Yang boleh di-embed ke Cognitive Store hanya `decision.md` yang sudah di-approve manusia dan dokumentasi final yang kodenya sudah di-merge ke `main`. Dilarang di-embed: chat/debat antar-agen, log error terminal & test gagal, draft yang belum di-approve.
2. **Pola Supersede (tombstone di SQLite).** Tabel `artifacts` memiliki kolom `superseded_by` (ID artifact pengganti). Saat keputusan baru menggantikan yang lama, record lama ditandai — bukan dihapus. Setiap ID hasil retrieval Vector DB wajib di-filter ulang ke SQLite: `superseded_by != NULL -> skip`. Dokumen basi tidak pernah masuk context LLM lagi.
3. **Time-decay scoring.** Skor akhir retrieval = `vector_similarity x faktor_umur` (mis. dokumen minggu ini x1.0, 3 bulan x0.5), dihitung deterministik di Go — dokumen lama yang kebetulan mirip kalah dari dokumen baru yang relevan.
4. **Ikat memori ke git commit / path.** Setiap entry memori menyimpan metadata `source_path` (mis. `crates/storage/src/nullifier.rs`) dan commit hash. Background GC mengecek via git: jika file/fungsi sudah dihapus atau di-rename di `main`, memori ditandai `stale` dan dibersihkan dari Vector DB.

Prinsip: Vector DB adalah **perpustakaan buku yang sudah lulus kurasi** — bukan tempat sampah. Edisi lama ditarik dari rak saat revisi terbit.

---

# 20. Memory Rules

Memory harus memiliki:

- source
- timestamp
- confidence
- scope
- owner

Jangan memasukkan semua chat ke memory secara otomatis — hanya keputusan ter-approve dan dokumentasi pasca-merge yang boleh di-embed (#19.6).

Memory harus memiliki lifecycle.

Contoh:

```text
raw event
    |
    v
candidate memory
    |
    v
validated memory
    |
    v
persistent memory
    |
    v
superseded / stale  (tombstone di SQLite — tidak pernah kembali ke context, #19.6)
```

---

# 21. Tools

Agent dapat memiliki tools.

Contoh:

```text
filesystem
shell
git
browser
search
http
database
terminal
python
docker
kubernetes
```

Tool access harus configurable per agent.

## 21.1 Tool Interface — MCP Client

Antarmuka tool agen menggunakan arsitektur **MCP Client**: Tool Runtime di backend Go bertindak sebagai client yang terhubung ke MCP server internal maupun eksternal (filesystem, shell, git, search, dst). Tool baru ditambahkan dengan mendaftarkan server MCP — bukan mengubah kode agen. Permission tetap di-gate deterministik oleh Policy Engine (#22) sebelum call diteruskan ke MCP server.

---
