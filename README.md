# SDLC Advisor

An agentic system that takes a free-text software project description and:

1. **lists the software requirements**: functional and non-functional, each traced to a quote from the description,
   plus regulatory requirements drawn from clauses retrieved out of official regulatory documents (RAG), each
   citing the document and page. Requirements that are still vague get multiple-choice clarifying questions;
2. **recommends an SDLC model**: it reads 14 project factors with evidence, and a documented rubric ranks Waterfall,
   V-Model, Spiral, Agile and DevSecOps, including hybrids. When the description is too thin, it asks clarifying
   questions instead of guessing;
3. optionally **writes a project-specific SDLC plan**, checks it and repairs it, and builds a compliance map and a
   risk register;
4. drafts a **Software Requirements Specification** structured after ISO/IEC/IEEE 29148: the narrative sections are
   written by the model (constraints cite the retrieved clauses), the requirement tables, regulations and
   traceability matrix are assembled deterministically. It exports to Markdown or prints to PDF.

It runs on a local Qwen3-4B model with a fine-tuned LoRA adapter for factor extraction. Gemini can optionally be
used for any stage.

## Layout

| Path | Contents |
|---|---|
| `agents/` | the agents and the orchestrator: requirements (description pass, RAG pass, multiple-choice clarifier), factor extraction, clarifying questions, plan, check, repair, SRS (`srs.py`) |
| `rubric/` | deterministic SDLC rubric: factors -> scores, ranking, hybrids |
| `compliance/` | standards retrieval (RAG), compliance map, risk register |
| `knowledge/` | document RAG: the list of official Indian regulatory documents (`sources.yaml`), the index builder and the passage index (`passages.jsonl`, `vectors.npy`) |
| `ontology/` | factor definitions, rubric, plan skeletons, roles, risks, and the standards knowledge base (`standards.yaml`) |
| `core/` | model backends (local, Gemini, OpenAI-compatible), paths, plan requirements and plan prompts |
| `eval/` | plan checker and obligation-coverage checks used by the repair step |
| `train/` | prompt formats and output parsing for the fine-tuned model; constrained decoding |
| `baselines/` | keyword-lexicon factor reader, used by the CPU-only server mode |
| `server/` | FastAPI backend for the web UI |
| `web/` | Next.js frontend (see `web/README.md`) |
| `runs/extract-qwen3-4b/adapter/` | the fine-tuned factor-extraction adapter (126 MB; not tracked by git, see below) |
| `examples/` | example scenarios and their saved runs (`examples/outputs/`) |
| `tests/` | unit and pipeline tests with mocked models (CPU only) |

## Setup

Python 3.11 and an NVIDIA GPU with at least 6 GB for the local model. The base models are downloaded from Hugging
Face on first use: `unsloth/Qwen3-4B-Instruct-2507-bnb-4bit` (2.5 GB, a 4-bit copy of Qwen3-4B-Instruct-2507) and
`BAAI/bge-small-en-v1.5` for retrieval. To use the original weights instead, pass
`--model-id Qwen/Qwen3-4B-Instruct-2507`.

```bash
pip install -r requirements-gpu.txt       # includes requirements.txt; install a CUDA build of torch first
npm --prefix web install
python -m pytest -q tests
```

## Regulatory documents (RAG)

`knowledge/sources.yaml` lists the official documents the system retrieves from:

| Standard | Document |
|---|---|
| `dpdp` | Digital Personal Data Protection Rules, 2025 (MeitY, Gazette G.S.R. 846(E)) |
| `certin` | CERT-In Directions under Section 70B(6) of the IT Act, 2022 |
| `gigw` | Guidelines for Indian Government Websites and Apps (GIGW) 3.0 |
| `rbi_kyc` | RBI (Commercial Banks - Know Your Customer) Directions, 2025, including video KYC (V-CIP) |
| `rbi_it_governance` | RBI Master Direction on IT Governance, Risk, Controls and Assurance Practices, 2023 |
| `rbi_digital_lending` | RBI (Digital Lending) Directions, 2025 |

The copies of the IT governance and digital lending directions on rbi.org.in are stamped "Withdrawn" (RBI
consolidated its directions by entity type in November 2025); they are kept as reference texts and labelled as such.

Each standard in `ontology/standards.yaml` carries curated obligations and a link to its document. For a project,
the standards that apply are found first (named in the text, or inferred by meaning; India-specific standards also
require an Indian marker such as RBI, Aadhaar or a rupee amount, both to be named and to be inferred). The regulate pass then retrieves the passages of
those documents closest to the description and its requirements (bge-small embeddings, cosine >= 0.62) and gives
them to the model alongside the obligations; every regulatory requirement cites an obligation or a passage with its
page. The compliance tab shows the source text behind each obligation.

The index is committed. To rebuild it after adding or updating PDFs (download them from the URLs in
`sources.yaml`, named as in its `file` fields):

```bash
python -m knowledge.build --pdf-dir path/to/pdfs
```

## Running

Command line:

```bash
python -m agents.cli --file examples/kyc_onboarding.txt --no-plan   # requirements + SDLC, about 3 minutes
python -m agents.cli --file examples/kyc_onboarding.txt             # also writes, checks and repairs a plan
python -m agents.cli --replay examples/outputs/kyc_onboarding.json  # print a saved run, no GPU needed
python -m agents.cli --file examples/india_video_kyc.txt --no-plan --srs srs.md   # also drafts the SRS
python -m agents.cli --file examples/kyc_short.txt --no-plan \
    --answers "regulatory_criticality=The central bank's KYC rules apply and its inspectors audit us"
```

Web UI (two processes, from this folder):

```bash
uvicorn server.app:app --port 8000        # loads the model at startup (about 1 minute)
npm --prefix web run dev                  # http://localhost:3000
```

Untick **Write an SDLC plan** in the UI for the fastest runs. Without a GPU, start the API with
`SDLC_BACKEND=lexicon` to use a keyword reader instead of the model (no requirements agent, no plan).

Gemini instead of the local model (set `GEMINI_API_KEY` first):

```bash
python -m agents.cli --file examples/kyc_onboarding.txt --no-plan --api gemini-2.5-flash
python -m agents.cli --file examples/kyc_onboarding.txt --api gemini-2.5-flash --api-stages requirements,plan
```

## Examples

| Scenario (`examples/`) | Requirements | Recommended SDLC |
|---|---|---|
| `kyc_onboarding` - bank onboarding, regulator review, legacy mainframe | 20 (17 from the text, 2 from FATF, 1 inferred) | V-Model with risk-driven prototyping cycles |
| `loan_decisioning` - lending rules change every few weeks, frequent deploys, sensitive data | 13 | DevSecOps with compliance gates |
| `regulatory_reporting` - fixed statutory format, fixed-price contract, audit sign-off | 20 | V-Model with phase-gate reviews |
| `community_events` - startup, weekly feedback and releases, no regulation | 11 | Agile |
| `india_video_kyc` - RBI-regulated bank, video KYC, Aadhaar and PAN | 29 (20 from the text, 8 from FATF, RBI KYC Directions and DPDP Rules, 1 inferred; 1 stated one linked to RBI KYC); 4 multiple-choice questions | Spiral, V-Model or DevSecOps (provisional, 3 of 14 factors stated) |
| `india_digital_lending` - NBFC loan app, Key Fact Statement, monthly rule changes | - | - |
| `india_gov_portal` - state scholarship portal under GIGW 3.0 | - | - |
| `kyc_short` - one sentence | 13 | none: asks four clarifying questions; with the answers, V-Model |

On an RTX 4050 (6 GB), requirements and the recommendation take 2-3 minutes without retrieved clauses and up to
20 minutes when several standards apply (the regulate pass reads their obligations and up to six passages); the SRS takes about 2 minutes; writing and
repairing a plan adds 3-17 minutes.

## The adapter and git

`runs/` is git-ignored because the adapter's weights file (126 MB) is over GitHub's 100 MB file limit. Copy
`runs/extract-qwen3-4b/adapter/` separately (for example as a release attachment), or track it with Git LFS:

```bash
git lfs install
git lfs track "runs/extract-qwen3-4b/adapter/*.safetensors"
```
