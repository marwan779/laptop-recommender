# Changelog

## [2.0.0](https://github.com/marwan779/laptop-recommender/compare/catalog-service-v1.0.0...catalog-service-v2.0.0) (2026-11-05)


### ⚠ BREAKING CHANGES

* **catalog-service:** Supersede legacy 14-table normalized schema with unified laptop_configuration, laptop_metrics, laptop_offer, store_scraping_pointer, and scraping_batch_log tables across 3 Alembic migrations.

### Features

* **catalog-service:** add logging subsystem, resilience boundaries, and api exception handlers ([ed650f0](https://github.com/marwan779/laptop-recommender/commit/ed650f0ab660027e1f7b33b3f370b9d74fa749e8))
* **catalog-service:** add main laptop scraping cron job, scheduler loop, and CLI runner ([c667595](https://github.com/marwan779/laptop-recommender/commit/c66759551060968dacc95bbce54c40e82becaa95))
* **catalog-service:** add price sync cron job and configure environment-based schedules ([da8642d](https://github.com/marwan779/laptop-recommender/commit/da8642d8d5f2ac6b6dbf36227fdcc6a17707fcbb))
* **catalog-service:** add price sync service with rollup aggregations and value recalibration ([32c7f3e](https://github.com/marwan779/laptop-recommender/commit/32c7f3e56950744a01e7e59662587a5667d9318d))
* **catalog-service:** create outbox message entity and alembic migration ([a41e6ee](https://github.com/marwan779/laptop-recommender/commit/a41e6eeeedc00f31ff21ff84314abe339e7a454a))
* **catalog-service:** implement 8-metric hardware engine and topsis input vectors ([110dbe6](https://github.com/marwan779/laptop-recommender/commit/110dbe64af4d21221165efa92e6c8d7f2bc91087))
* **catalog-service:** implement catalog ingestion pipeline and database seeder repository ([c9c782a](https://github.com/marwan779/laptop-recommender/commit/c9c782a05070ea083ce783f110cd047c5811258d))
* **catalog-service:** implement clean architecture catalog ingestion pipeline and database seeder ([4f82bb3](https://github.com/marwan779/laptop-recommender/commit/4f82bb3dbe308a6966eface01aa0e4b4cd001711))
* **catalog-service:** implement message consumer and wire rabbitmq into app lifespan ([fed2d83](https://github.com/marwan779/laptop-recommender/commit/fed2d834f38399f1837cba47c1a8a66754654e3f))
* **catalog-service:** implement object storage contract and aws s3 provider ([1c2fcb1](https://github.com/marwan779/laptop-recommender/commit/1c2fcb160273d5870c85dbc3e7deb117e28a8731))
* **catalog-service:** implement object storage contract, s3 adapter, and unpopulated env config ([8eb4267](https://github.com/marwan779/laptop-recommender/commit/8eb4267108889359dad2a1fc2487bbd0c0040a4b))
* **catalog-service:** implement outbox relay worker and producer integration ([e2e75e9](https://github.com/marwan779/laptop-recommender/commit/e2e75e90612a4be0846e32cea7ec66543be0ad48))
* **catalog-service:** implement rabbitmq broker driver and event schemas ([082c631](https://github.com/marwan779/laptop-recommender/commit/082c631ac44108069a2600d1f87f45566cf8f2d9))
* **catalog-service:** implement transactional outbox repository with row locking ([4bb6008](https://github.com/marwan779/laptop-recommender/commit/4bb6008534999f322c5e8a051ac872ab967830a4))
* **catalog-service:** modernize async db layer, scoring models, and tooling ([9523bac](https://github.com/marwan779/laptop-recommender/commit/9523bac89ce16d77101bb7d6d3c3fade14f2816c))
* **catalog-service:** restructure database schema to strongly-typed specs and metrics ([841e2f5](https://github.com/marwan779/laptop-recommender/commit/841e2f59d293d16ad9eb15f52760e555a2fcdb31))
* implement 8-metric hardware scoring engine, icecat spec enrichment, and core catalog infrastructure ([c787f06](https://github.com/marwan779/laptop-recommender/commit/c787f0693732da13e711b374bcd1c9df5e0117f7))
* implement lightweight price monitor worker, catalog sync, and cron schedulers ([99bc74a](https://github.com/marwan779/laptop-recommender/commit/99bc74a3ee46aa175119142ad07b23e4619211e4))
* **messaging:** implement rabbitmq event-driven pipeline and transactional outbox ([d74b183](https://github.com/marwan779/laptop-recommender/commit/d74b183006058bfd64cbba3cca887f7b05e6bb15))
* **pipeline:** enrich catalog with deterministic hardware metrics and preserve store pointers ([1361269](https://github.com/marwan779/laptop-recommender/commit/1361269fb1b2f101ce07292786f59c0af7ca25c6))
* **pipeline:** integrate icecat spec enrichment and post-combiner targeted llm workflow ([9823edd](https://github.com/marwan779/laptop-recommender/commit/9823edd6ad979f5e90992f2679c82ab4e79634ff))


### Bug Fixes

* **pipeline:** resolve audit findings on power margins, displays, inputs, and catalog deduplication ([16b8188](https://github.com/marwan779/laptop-recommender/commit/16b8188958156fa0651007227bbb83ec2b326a41))
