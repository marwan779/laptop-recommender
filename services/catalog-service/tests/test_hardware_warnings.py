from app.domain.hardware_warnings import inject_legacy_hardware_cons


def test_inject_legacy_hardware_cons_adds_ddr4_and_hdd_without_duplicates():
    en, ar = inject_legacy_hardware_cons(
        ["Plastic lid"],
        ["غطاء بلاستيكي"],
        ram_type="DDR4",
        storage_type="HDD",
    )

    assert len(en) == 3
    assert len(ar) == 3
    assert any("DDR4" in item for item in en)
    assert any("HDD" in item for item in en)

    # Idempotent if called twice
    en2, ar2 = inject_legacy_hardware_cons(en, ar, ram_type="DDR4", storage_type="HDD")
    assert en2 == en
    assert ar2 == ar


def test_inject_legacy_hardware_cons_skips_ddr5_and_ssd():
    en, ar = inject_legacy_hardware_cons(
        ["Heavy charger"],
        ["شاحن ثقيل"],
        ram_type="DDR5",
        storage_type="SSD",
    )

    assert en == ["Heavy charger"]
    assert ar == ["شاحن ثقيل"]
