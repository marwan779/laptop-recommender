# Changelog

## [2.1.0](https://github.com/marwan779/laptop-recommender/compare/catalog-service-v2.0.0...catalog-service-v2.1.0) (2026-11-14)


### Features

* **cache:** add redis response caching layer with exact-match request keys ([2a16656](https://github.com/marwan779/laptop-recommender/commit/2a16656c00547ef344dcde0c8b822e62e0a356b8))
* **cache:** implement in-memory cache provider and interface contract ([cebb303](https://github.com/marwan779/laptop-recommender/commit/cebb3034336cf814c5fac4faa567323c9bf0b93a))
* **cache:** implement Redis cache provider and integrate with middleware ([e8c2657](https://github.com/marwan779/laptop-recommender/commit/e8c2657aed444dfd0a87d4c68607d4fffe7114f3))
* **catalog-service:** add topsis multi-criteria recommendation domain engine ([fb7bde0](https://github.com/marwan779/laptop-recommender/commit/fb7bde0e50be69323c14f263a5ca1f935bc34e36))
* **catalog-service:** implement topsis recommendation application service and api endpoint ([8dedf3e](https://github.com/marwan779/laptop-recommender/commit/8dedf3eaa37c5bee11c441c23d77390e80a03908))
* **catalog:** add full laptop detail endpoint and store offer links ([1f83ccb](https://github.com/marwan779/laptop-recommender/commit/1f83ccb8b56e01e3985de245f298e50443a8c060))
* **catalog:** add laptop detail endpoint, offer freshness, and redis setup ([9e2f7a4](https://github.com/marwan779/laptop-recommender/commit/9e2f7a475631ca2acc466f518afbc3edd641acf6))
* **catalog:** add multi-store price history tracking and telemetry chart ([3c8bbfe](https://github.com/marwan779/laptop-recommender/commit/3c8bbfebdd85958c0f8527f21c911880f9082f77))
* **catalog:** add optional real-world experience and hardware metric filters ([c96ab84](https://github.com/marwan779/laptop-recommender/commit/c96ab848c0aa4556fb25de0b1c7de4d6cf6f8f8c))
* **catalog:** aggregate chassis review targets and emit reviews scrape command via outbox ([af394c4](https://github.com/marwan779/laptop-recommender/commit/af394c4379fb4ef7db525a37fba964120dff2710))
* **catalog:** implement deterministic keyset cursor pagination ([562528c](https://github.com/marwan779/laptop-recommender/commit/562528c1adf39cc2c1be90b72a4f84baa04c25d0))
* **catalog:** persist strongly-typed review intelligence and aspect scores ([b3e39b5](https://github.com/marwan779/laptop-recommender/commit/b3e39b514c26c78a9a523065a34d2f99c0d34d85))
* **frontend:** add catalog search, recommendation hardware filters, and top_k control ([b7c0d9f](https://github.com/marwan779/laptop-recommender/commit/b7c0d9fda77e6b6e885b53af065026c2a4211e47))
* **frontend:** add multi-persona blending, 35+ specs modal, and 15-metric disclosure ([1a0ae49](https://github.com/marwan779/laptop-recommender/commit/1a0ae498a2b44ef36be43268ce4471301d6dac7f))
* **frontend:** introduce verified instrument workbench, api gateway, and price telemetry ([15bfca2](https://github.com/marwan779/laptop-recommender/commit/15bfca23701b534b8f16d4174c89b60024fdb48e))
* **messaging,catalog-service:** harden transactional inbox/outbox, retire internal cron loops, and fix stage-2 review & price-cache flows ([dc3d9b0](https://github.com/marwan779/laptop-recommender/commit/dc3d9b0d9f4d4209159d49171f92a842c3c83d73))
* **messaging:** implement transactional inbox, redis deduplication, and outbox lease recovery ([ac667ac](https://github.com/marwan779/laptop-recommender/commit/ac667ac0c8baa8126f74a70513eab52fcb4a1c34))
* **recommender:** implement TOPSIS engine, recommendation API, and full laptop detail endpoint ([902b08b](https://github.com/marwan779/laptop-recommender/commit/902b08b07ead83478a50b6c1e6065e4d7d45d9af))
* **reviews:** add review collector orchestrator with s3 upload and event dispatch ([6782423](https://github.com/marwan779/laptop-recommender/commit/678242315041e77a95aac1936721d27eaffb9558))
* **reviews:** add screen size to targets and multi-platform community scrapers ([df264d2](https://github.com/marwan779/laptop-recommender/commit/df264d2b0aece23c589b8f4c4ffc459cf9a3a135))
* **reviews:** carry matched chassis ids in review targets and add s3 reviews schema ([ff17a9b](https://github.com/marwan779/laptop-recommender/commit/ff17a9b669f0c8c6aef5bf5d627a5d73c033e0a2))
* **reviews:** implement review target identity extraction and batching schemas ([44bc93b](https://github.com/marwan779/laptop-recommender/commit/44bc93bd93130d7aee96b918c7af31f1e082dfe3))


### Bug Fixes

* **catalog-service:** defer review ingestion commit and reviewed flags until stage 2 ([39a1a1b](https://github.com/marwan779/laptop-recommender/commit/39a1a1bef0ae893918e4e151ea733115fa8092ae))
* **docker:** add greenlet for sqlalchemy asyncio and configure frontend nginx api proxy ([c6589f3](https://github.com/marwan779/laptop-recommender/commit/c6589f32592222197d1da19ead8ed469ec3b0f3c))
* **pricing:** add outbox cron dispatch and correct frontend telemetry display ([3dec2c3](https://github.com/marwan779/laptop-recommender/commit/3dec2c3562c979b6bb38b1b9eb3d9827829e9f7b))
* **recommender:** enforce persona-aware fallback, aaa intent parsing, and 1:1 review alignment ([1090310](https://github.com/marwan779/laptop-recommender/commit/1090310567b5c18a2f13800f9a7ca0b22c1ac5c4))
* **recommender:** resolve nested aspect scores and guard banner price formatting ([52caf8a](https://github.com/marwan779/laptop-recommender/commit/52caf8a6fc7ea116d3cb1d63db09e3d44572b2b5))
* **reviews:** harden chassis grouping, deduplication, relevance filtering, and cookieless youtube scraping ([1e1dfd6](https://github.com/marwan779/laptop-recommender/commit/1e1dfd638549e11037b2ab59ee80c1290f8a201e))
* **reviews:** harden chassis key grouping, relevance filtering, deduplication, and cookieless scraping ([07efc07](https://github.com/marwan779/laptop-recommender/commit/07efc0739eaf5aa4f0409de5b00de74eef144c4c))

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
