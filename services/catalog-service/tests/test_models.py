import uuid

from app.models.components import CPU, GPU, UsageCategory
from app.models.configuration import LaptopCategoryScore, LaptopOffer
from app.models.laptop import Brand, LaptopConfiguration, LaptopFamily, LaptopModel


def test_cpu_model_instantiation():
    cpu = CPU(
        manufacturer="Intel",
        name="Core i7-13620H",
        architecture="Raptor Lake",
        cores=10,
        threads=16,
        base_power_w=45,
        cinebench_r23_single=1820,
        cinebench_r23_multi=15400,
        single_core_rating=75.0,
        multi_core_rating=68.0,
    )
    assert cpu.name == "Core i7-13620H"
    assert cpu.cinebench_r23_single == 1820
    assert cpu.single_core_rating == 75.0


def test_gpu_model_instantiation():
    gpu = GPU(
        manufacturer="NVIDIA",
        name="GeForce RTX 4060 Laptop GPU",
        vram_gb=8.0,
        integrated=False,
        timespy_graphics=10450,
        gaming_rating=70.0,
        creative_compute_rating=68.0,
        tdp_min_w=35.0,
        tdp_max_w=140.0,
    )
    assert gpu.name == "GeForce RTX 4060 Laptop GPU"
    assert gpu.timespy_graphics == 10450
    assert gpu.tdp_max_w == 140.0


def test_laptop_configuration_and_scores_instantiation():
    config_id = uuid.uuid4()
    cat_id = uuid.uuid4()

    config = LaptopConfiguration(
        id=config_id,
        laptop_model_id=uuid.uuid4(),
        canonical_id="lenovo_legion_pro_5_16irx8_rtx4060",
        manufacturer_part_number="82WK0046US",
        identity_hash="hash_test_123",
        title="Lenovo Legion Pro 5 16IRX8",
        min_price_egp=65000.0,
        cheapest_store="Compumarts",
        hardware_score=82.5,
        cpu_id=uuid.uuid4(),
    )

    offer = LaptopOffer(
        laptop_configuration_id=config_id,
        store_name="Compumarts",
        retailer_sku="82WK0046US",
        price_egp=65000.0,
        in_stock=True,
    )

    score = LaptopCategoryScore(
        laptop_configuration_id=config_id,
        usage_category_id=cat_id,
        score=8.5,
        raw_percentile=85.0,
        notes="High TGP RTX 4060 with strong multi-threaded CPU",
    )

    assert config.canonical_id == "lenovo_legion_pro_5_16irx8_rtx4060"
    assert offer.price_egp == 65000.0
    assert score.score == 8.5
