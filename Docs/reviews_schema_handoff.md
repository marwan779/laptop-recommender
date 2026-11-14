# Phase 2 Reviews Schema Gap & Service Handoff

**Scope:** Contract comparison between what `scraper-service` produces vs. what `ai-recommender-service` and `catalog-service` currently accept, and why an automated **Raw -> Enriched** conversion step is required for production.

---

## 1. Executive Summary

- **`scraper-service` outputs raw scraped text:** YouTube video metadata, raw spoken transcripts, top comments, editorial reviews (when available), and community forum discussions.
- **`ai-recommender-service` (`chroma_reviews_engine.py`) and `catalog-service` (`ReviewIntelligenceService`) expect already-enriched NLP profiles:** Pre-separated bilingual `pros`/`cons`, `community_nlp_score`, and 5 numeric `aspect_scores`.
- **Current gap:** Nothing inside `services/ai-recommender-service` currently reads `"youtube"` or `"communities"`. Passing the raw scraper JSON directly into `/ingest-reviews` causes `chroma_reviews_engine.py` to skip recalibration (`aspect_scores` missing), fall back to `75.0`, and index **0 ChromaDB vectors** (and `catalog-service` returns `SKIPPED`).
- **Why this happened:** During v6 prototyping, `cleaned_and_enriched_chassis_reviews_v6.json` and `reviews_deduplicated_v6.json` were enriched externally before being loaded into `ai-recommender-service`. To automate weekly Phase 2 runs in production, we must implement the **Raw -> Enriched** stage in code.

---

## 2. Format A: What `scraper-service` Outputs (Raw JSON)

This is the raw structure produced per chassis by `scraper-service`:

```json
{
  "laptops": [
    {
      "chassis_key": "asus:tuf-gaming:asus-tuf-gaming-a16-fa608pm-rv169w",
      "primary_laptop_id": "f7a97745-0a02-4f5f-b2f5-299faaa80073",
      "primary_canonical_id": "laptop_asus_tuf_gaming_90nr0mc1m003t0",
      "matched_laptop_ids": [
        "f7a97745-0a02-4f5f-b2f5-299faaa80073"
      ],
      "matched_canonical_ids": [
        "laptop_asus_tuf_gaming_90nr0mc1m003t0"
      ],
      "identity": {
        "brand": "ASUS",
        "laptop_family": "Tuf Gaming",
        "laptop_model": "ASUS TUF Gaming A16 FA608PM-RV169W",
        "sub_model": null,
        "aggregated_mpns": ["90NR0MC1M003T0"],
        "aggregated_skus": [
          "90NR0MC1-M003T0",
          "FA608PM-RV169W",
          "90NR0MC1-M003T"
        ]
      },
      "youtube": {
        "query_used": "ASUS Tuf Gaming A16 FA608PM-RV169W review",
        "total_videos_found": 3,
        "videos": [
          {
            "video_id": "A0Qui0XNn7Q",
            "title": "Asus TUF A16 (2025) REVIEW - The CHEAPEST 2025 Gaming Laptop!",
            "channel_name": "Crimson Tech",
            "duration_seconds": 696,
            "view_count": 306267,
            "language": "en",
            "transcript_text": "...long unstructured spoken transcript (or empty string)...",
            "transcript_segments": [],
            "top_comments": [
              {
                "author": "@esteh24",
                "comment_text": "damn 2025 budget is not the same budget anymore",
                "like_count": 488
              },
              {
                "author": "@nathanlim3477",
                "comment_text": "@Bdriley-bs7gs can it run black myth wukong bro?",
                "like_count": 0
              }
            ]
          }
        ]
      },
      "communities": {
        "reddit": [],
        "facebook": [],
        "editorial": [
          {
            "source": "example-editorial",
            "rating": 4.0,
            "pros": [
              "Bright display",
              "Solid speakers",
              "Strong gaming performance"
            ],
            "cons": [
              "Battery life could be better",
              "Fans get loud under heavy load"
            ],
            "verdict": "Short editorial summary paragraph..."
          }
        ],
        "discussions": [
          {
            "platform": "level1techs",
            "post_title": "How to limit charging percentage on my Asus TUF Gaming A16 to 80%?",
            "post_body": "Hi, how to limit charging percentage to 80%? I wanna prolong battery life..."
          }
        ]
      }
    }
  ]
}
```

### Characteristics of Raw Output
- **Unstructured prose:** Transcripts and forum posts mix useful hardware feedback with greetings, sponsor segments, and support questions.
- **No polarity separation on transcripts/comments/discussions:** Complaints and praise appear mixed together (only `editorial`, when present, separates `pros` and `cons`).
- **No aspect breakdown:** No `0-100` numeric scores for thermals, acoustics, build, keyboard, or battery.
- **English-only / noisy chatter:** Requires noise filtering and summary extraction before showing on product cards.

---

## 3. Format B: What `ai-recommender-service` & `catalog-service` Expect

`chroma_reviews_engine.py` accepts two enriched schemas: the **`"laptops"` schema** (`cleaned_and_enriched_chassis_reviews_v6.json`, which `catalog-service`'s `ReviewIntelligenceService` also consumes directly for PostgreSQL), and the **`"chassis_reviews"` schema** (`reviews_deduplicated_v6.json`).

### B1. Primary Shared Contract (`"laptops"` + `"nlp_review_profile"`)

```json
{
  "laptops": [
    {
      "chassis_key": "asus:tuf-gaming:asus-tuf-gaming-a16-fa608pm-rv169w",
      "primary_canonical_id": "laptop_asus_tuf_gaming_90nr0mc1m003t0",
      "matched_canonical_ids": [
        "laptop_asus_tuf_gaming_90nr0mc1m003t0"
      ],
      "identity": {
        "brand": "ASUS",
        "laptop_family": "Tuf Gaming",
        "laptop_model": "ASUS TUF Gaming A16 FA608PM-RV169W"
      },
      "nlp_review_profile": {
        "community_nlp_score": 82.0,
        "aspect_scores": {
          "thermals_score": 76.0,
          "acoustics_score": 71.0,
          "build_and_hinges_score": 84.0,
          "keyboard_and_trackpad_score": 79.0,
          "real_battery_and_reliability_score": 83.0
        },
        "pros_en": [
          "Military-grade MIL-STD-810H chassis with aluminum/reinforced lid and durable hinges",
          "Dual Arc Flow fans with 5 heatpipes sustain full 115W RTX 5060 performance without frame drops",
          "Easy upgradeability with 2x M.2 slots, 2x DDR5 SO-DIMM slots, and strong battery life (90Wh)"
        ],
        "pros_ar": [
          "شاسيه قوي بمعيار عسكري MIL-STD-810H ومفصلات متينة تتحمل الاستخدام اليومي الشاق",
          "مراوح Arc Flow المزدوجة مع 5 أنابيب حرارية تحافظ على كامل قوة RTX 5060 (115W) بدون سقوط فريمات",
          "قابلية تطوير ممتازة (2 فتحات M.2 وفتحتين رام DDR5) مع بطارية جيدة (90Wh)"
        ],
        "cons_en": [
          "CPU temperatures can reach 90-95C under heavy stress tests in warm rooms",
          "Turbo fan profile is loud during heavy AAA gaming"
        ],
        "cons_ar": [
          "حرارة المعالج ترتفع إلى حدود 90-95 درجة عند الضغط الشديد في الغرف الحارة",
          "صوت المراوح يكون مرتفعاً على وضع Turbo أثناء الألعاب الثقيلة"
        ]
      }
    }
  ]
}
```

### B2. Alternative Contract Accepted by `ai-recommender-service` (`"chassis_reviews"`)

Used in `reviews_deduplicated_v6.json`: replaces `nlp_review_profile` at the item root with:
- `community_nlp_score` (float)
- `aspect_scores` (same 5 keys as above)
- `clean_profile_lists`: `{ "pros_en": [], "pros_ar": [], "cons_en": [], "cons_ar": [] }`
- `deduplicated_chunks`: `[{ "text", "polarity": "pro"|"con", "source_type", "aspects": [] }]`

---

## 4. Why Raw Data Cannot Be Embedded Directly in ChromaDB

Inside `services/ai-recommender-service`, the retrieval and scoring architecture depends on clean separation before indexing:

1. **ChromaDB stores exactly 2 documents per chassis (`chroma_reviews_engine.py`):**
   - `{chassis_key}__pro`: `" | ".join(pros_ar + pros_en)` (`polarity = "pro"`)
   - `{chassis_key}__con`: `" | ".join(cons_ar + cons_en)` (`polarity = "con"`)
2. **Query-time scoring requires Pro vs. Con contrast (`recommendation_pipeline.py`):**
   - When a user submits a prompt, Jina-v3 queries `__pro` and `__con` separately and calculates:
     - `net_sim = cosine(query, pros) - 0.75 * cosine(query, cons)`
     - `adjusted_nlp_score = clamp(35.0 .. 98.0, community_nlp_score + net_sim * 32.0)`
   - If positive and negative claims are mixed in one raw transcript, embeddings cannot separate praise from complaints, breaking the penalty term (`- 0.75 * con_sim`).
3. **512-dim vector dilution:** Long transcripts, greetings, and unrelated user questions dilute a single 512-dimensional Jina-v3 vector so real hardware pros/cons lose signal.
4. **SQL & Frontend contract (`catalog-service`):** PostgreSQL stores `aspect_scores`, `community_nlp_score`, and aligned bilingual `pros`/`cons` lists to render directly on laptop cards and compute TOPSIS rankings.

---

## 5. Production Pipeline & Missing Bridge

```text
scraper-service
   |  (uploads Raw Format A: youtube + communities)
   v
[ MISSING STAGE: Raw -> Enriched Converter ]
   |  1. Filter chatter / forum questions / non-review noise
   |  2. Deduplicate claims across YouTube, editorial & discussions
   |  3. Extract separated Pros/Cons + 5 aspect_scores + community_nlp_score
   v
ai-recommender-service
   |  (embeds __pro & __con into Jina-v3 ChromaDB + uploads Format B1 to S3)
   v
catalog-service
   |  (ingests Format B1 into PostgreSQL via ReviewIntelligenceService)
```

### Engineering Decision Needed
Because free-tier cloud LLM quotas will not cover large initial batches or reliable production runs, the team needs to align on how the **Raw -> Enriched Converter** will be implemented inside `ai-recommender-service`:
1. **Zero-LLM Extractive Pipeline (Python + Jina-v3 already in RAM):** Rules/regex noise gate + Jina-v3 zero-shot aspect polarity anchors + `editorial.pros`/`cons` + highest-confidence extractive review sentences (with English fallback or lightweight local `en->ar` translation if Arabic UI bullets are required).
2. **Offline / Local Batch LLM Worker (or low-cost paid API key):** Runs only during weekly batch ingestion on new/updated chassis outside the web container's 4.5 GiB memory budget.
