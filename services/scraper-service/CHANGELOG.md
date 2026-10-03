# Changelog

## [1.2.0](https://github.com/marwan779/laptop-recommender/compare/scraper-service-vv1.1.0...scraper-service-vv1.2.0) (2026-10-03)


### Features

* **scraper:** add /version metadata endpoint ([a31b920](https://github.com/marwan779/laptop-recommender/commit/a31b9202f64c2579a3968f785c6a7f867f6abe6e))

## [1.1.0](https://github.com/marwan779/laptop-recommender/compare/scraper-service-vv1.0.0...scraper-service-vv1.1.0) (2026-10-02)


### Features

* adding HP scraping service with Level 1 and Level 2 deep specs extraction ([fb4056f](https://github.com/marwan779/laptop-recommender/commit/fb4056f5332b0af76f0438e8a002ebae0977149a))
* adding Lenovo scrapping service. ([320f5b3](https://github.com/marwan779/laptop-recommender/commit/320f5b317801e8543d7df4920633e79175643922))
* **api:** implement asynchronous scraping endpoint and enhance request handling ([7ab485a](https://github.com/marwan779/laptop-recommender/commit/7ab485a8f12ec7a15a6bcace2f0e176f74f4d697))
* **docker:** update scrper service docker file to use multi stage to minimize image size, use non root user for security ([24f872b](https://github.com/marwan779/laptop-recommender/commit/24f872bd1f90a73743f6fd784391ca1a04dda833))
* implement 2B Egypt store scraper with Level 1, Level 2 specs, and watermark stopping ([1a5c602](https://github.com/marwan779/laptop-recommender/commit/1a5c6029dcb0247bfc3c3bfff5efc327bc55e72c))
* implement Compumarts store scraper with Level 1, Level 2 deep specs, and watermark stopping ([8fd426a](https://github.com/marwan779/laptop-recommender/commit/8fd426a79a7adb6b504bda63c11c2ab5319f35f0))
* implement El Badr Group store scraper with Level 1, Level 2 specs, and date_added watermark stopping ([36373aa](https://github.com/marwan779/laptop-recommender/commit/36373aa90b941153fd4e118fede2c96b8e8acde3))
* implement Sigma Computer store scraper with Level 1, Level 2 specs, and created_at watermark stopping ([8cb1bb9](https://github.com/marwan779/laptop-recommender/commit/8cb1bb9387b895da9b3fce2efa82ea06fc419723))
* **orchestrator:** bypass local disk persistence when upload_to_bucket is True to conserve server storage ([11ea33e](https://github.com/marwan779/laptop-recommender/commit/11ea33e1e76b9908919092dc3245f8f124e1027d))
* **scraper:** add latest_pointers to StoreCatalogResult and store scrapers ([9dc81a9](https://github.com/marwan779/laptop-recommender/commit/9dc81a95cb48c9233a65668cbc2dabe0a9f2d080))
* **scraper:** add ScrapeOrchestrator abstraction layer with unified BrandCatalogResult ([7214484](https://github.com/marwan779/laptop-recommender/commit/7214484ffd1e1c90fca2fdce985720d558a589c8))
* **scraper:** adopt pyproject.toml unifying mutmut, pytest, and coverage configurations ([8394a4e](https://github.com/marwan779/laptop-recommender/commit/8394a4ec33de8a2d02b711cadafee7d947e08813))
* **scraper:** enhance brand scraping logic and improve error handling for HP and GigaByte ([f206ccd](https://github.com/marwan779/laptop-recommender/commit/f206ccd8f93a2cf054aa80d96e7587461f307a86))
* **scraper:** enhance skipped laptop tracking and reporting across scrapers ([1008fe4](https://github.com/marwan779/laptop-recommender/commit/1008fe4b79b6ae5b752b6fa7a7bc3f90d3f43ccc))
* **scraper:** implement GigaByte brand scraper with Level 1 and Level 2 specs ([dfe9952](https://github.com/marwan779/laptop-recommender/commit/dfe99523309e63fbdc11f22a72edb92bd922f6d3))
* **scraper:** implement Tradeline Egypt store scraper with Level 1 and 2 specs ([312cca3](https://github.com/marwan779/laptop-recommender/commit/312cca3dae99e1e512e9d32e1b6daf3f380c1099))
* **scraper:** normalize max_pages handling and improve display messages across scrapers ([ee09e26](https://github.com/marwan779/laptop-recommender/commit/ee09e26774dede269c30bc988871308de8b51bd3))
* **scrapers:** implement Amazon, Noon, and B.TECH Egypt store scrapers ([5f5ed9d](https://github.com/marwan779/laptop-recommender/commit/5f5ed9d50356b13fdf34035aba89d9664155304f))
* **scraper:** update HP store data with new laptop details and remove end_date parameter ([4ab1472](https://github.com/marwan779/laptop-recommender/commit/4ab1472cbdeafe204e5b2d5c7b4f1915f4427a26))
* sort 2B catalog by Magento auto-incrementing entity_id descending for true chronological newest-first crawling and watermark stopping ([7d89ab7](https://github.com/marwan779/laptop-recommender/commit/7d89ab74eabcc917ea8ffed2b92fd4fd753e9c14))
* **storage:** add initial storage service implementation and dependency injection ([37e7f7d](https://github.com/marwan779/laptop-recommender/commit/37e7f7d1a3c3f45291fbe97081af1405170c8880))
* **storage:** implement object storage abstraction layer with AWS S3 provider and orchestrator integration ([d6000ce](https://github.com/marwan779/laptop-recommender/commit/d6000cebcc9276602b1cf3a79920fac53dd77ac5))
* **tradeline_store_service:** add macbook neo collection ([1c938b2](https://github.com/marwan779/laptop-recommender/commit/1c938b2d422519fb216a40ecc07822e68d94763d))
* **tradeline:** enhance accessory filtering and add skipped records logging ([02d300d](https://github.com/marwan779/laptop-recommender/commit/02d300d4147f70b45904c5afd893e6d13b467a3a))


### Bug Fixes

* **deps:** add beautifulsoup4 dependency and scraper test outputs ([4613c84](https://github.com/marwan779/laptop-recommender/commit/4613c8460a6672a46433155db0a528c307f184bd))
* **deps:** add boto3 dependency for AWS S3 object storage integration ([2f88cb8](https://github.com/marwan779/laptop-recommender/commit/2f88cb85b4ff58a896fa646f3121b74829da8cb1))
* **dockerfile:** add layer to install playwright chromium binaries that is needed for some stores and brands ([41fbc3c](https://github.com/marwan779/laptop-recommender/commit/41fbc3c030d2fe1dc687db0001c263c24ce1a1aa))
* **mutmut:** configure source_paths for app package and use mutmut results in pipeline ([f8b3658](https://github.com/marwan779/laptop-recommender/commit/f8b36585776775d206f3ae7b5534bcc0099f0897))
* **mutmut:** update pyproject.toml to source_paths and remove deprecated tests_dir ([1cbf723](https://github.com/marwan779/laptop-recommender/commit/1cbf723537f8835a2a91f44e8a8d7a3ac1dbfbcd))
* **orchestrator:** upload to object storage before dispatching background email notification ([594dc03](https://github.com/marwan779/laptop-recommender/commit/594dc032cb78f65280f94e04705deb3ef9093771))
* **scraper:** implement true multi-page pagination for ASUS via Odin Shop API ([85455ce](https://github.com/marwan779/laptop-recommender/commit/85455ce58ab3096d5a066b30f322354732fb19ce))
* **scraper:** import missing IObjectStorageService in deps.py ([9432f2f](https://github.com/marwan779/laptop-recommender/commit/9432f2ff2a282809cd1a0c3b4ef262b94efa584d))
* **scrapers:** resolve B.TECH Next.js RSC and Noon catalog ingestion with improved accessory filtering ([12687a7](https://github.com/marwan779/laptop-recommender/commit/12687a7feb166a9e3438d80b9bf635c4200dfa43))
* unify robust _is_standalone_accessory filtering across all store scrapers ([4a54139](https://github.com/marwan779/laptop-recommender/commit/4a54139eb35b085e88a86f435802bad3517d1828))
* Update store imports to app.core.normalizer and configure scraper-service Python interpreter ([3558708](https://github.com/marwan779/laptop-recommender/commit/3558708420cab7f42ef0a5cec599da78588bfe21))


### Performance Improvements

* **scraper:** optimize mutation testing speed and re-enable release-please main gate ([068edf4](https://github.com/marwan779/laptop-recommender/commit/068edf4b9e19d964bea8de94e6d01c612cd771f4))


### Documentation

* clarify 2B catalog uses Magento position/Most Selling sorting rather than chronological date ([7f505ce](https://github.com/marwan779/laptop-recommender/commit/7f505ce3afd57610a37e8a35f3c22c2a488cc138))
* **tasks:** add task specification for Amazon, Noon, and B.TECH Egypt store scrapers and add Tradeline scraping results ([a37c18b](https://github.com/marwan779/laptop-recommender/commit/a37c18bea05e69a52544ab0d3641ff9f8a288b9f))
