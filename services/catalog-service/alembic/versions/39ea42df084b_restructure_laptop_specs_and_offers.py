"""restructure_laptop_specs_and_offers

Revision ID: 39ea42df084b
Revises: b2138ccd2e9e
Create Date: 2026-11-03 22:45:35.384204

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "39ea42df084b"
down_revision: Union[str, Sequence[str], None] = "b2138ccd2e9e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Restructure laptop_configuration to store complete specifications and pricing,

    update laptop_offer, and drop obsolete normalized component tables.
    """
    # 1. Drop dependent tables that referenced laptop_configuration
    for table_name in [
        "laptop_category_score",
        "laptop_configuration_alias",
        "laptop_memory",
        "laptop_storage_slot",
        "laptop_storage",
        "battery",
        "laptop_connectivity",
        "laptop_port",
        "laptop_build",
        "laptop_measurement",
        "laptop_thermals",
        "laptop_audio",
        "laptop_webcam",
        "specification_evidence",
        "raw_laptop_record",
        "memory_module",
        "storage_device",
        "usage_category",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE;")

    # 2. Update laptop_offer: drop data_source_id foreign key & add tracking columns
    op.execute("ALTER TABLE laptop_offer DROP CONSTRAINT IF EXISTS laptop_offer_data_source_id_fkey CASCADE;")
    op.execute("ALTER TABLE laptop_offer DROP COLUMN IF EXISTS data_source_id CASCADE;")

    op.add_column("laptop_offer", sa.Column("mpn", sa.String(length=100), nullable=True))
    op.add_column("laptop_offer", sa.Column("previous_price_egp", sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column(
        "laptop_offer",
        sa.Column("is_valid_price", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.add_column(
        "laptop_offer",
        sa.Column("price_updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column(
        "laptop_offer",
        sa.Column("last_checked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 3. Drop legacy foreign keys and columns on laptop_configuration
    for fk_name in [
        "laptop_configuration_cpu_id_fkey",
        "laptop_configuration_gpu_id_fkey",
        "laptop_configuration_display_id_fkey",
        "laptop_configuration_laptop_model_id_fkey",
    ]:
        op.execute(f"ALTER TABLE laptop_configuration DROP CONSTRAINT IF EXISTS {fk_name} CASCADE;")

    for col in [
        "cpu_id",
        "gpu_id",
        "display_id",
        "laptop_model_id",
        "identity_hash",
        "hardware_score",
        "portability_score",
        "battery_hours_estimate",
        "upgradeability_score",
        "manufacturer_part_number",
    ]:
        op.execute(f"ALTER TABLE laptop_configuration DROP COLUMN IF EXISTS {col} CASCADE;")

    # 4. Drop legacy parent component tables
    for table_name in ["cpu", "gpu", "display", "laptop_model", "laptop_family", "brand", "data_source"]:
        op.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE;")

    # 5. Add strongly-typed hardware specifications and lifecycle columns to laptop_configuration
    # Identity & presentation
    op.add_column("laptop_configuration", sa.Column("mpn", sa.String(length=100), nullable=True))
    op.add_column(
        "laptop_configuration", sa.Column("brand", sa.String(length=50), nullable=False, server_default="Generic")
    )
    op.add_column("laptop_configuration", sa.Column("laptop_family", sa.String(length=100), nullable=True))
    op.add_column(
        "laptop_configuration",
        sa.Column("laptop_model", sa.String(length=150), nullable=False, server_default="Generic Model"),
    )
    op.add_column("laptop_configuration", sa.Column("base_color", sa.String(length=50), nullable=True))
    op.add_column("laptop_configuration", sa.Column("color", sa.String(length=50), nullable=True))
    op.add_column(
        "laptop_configuration",
        sa.Column("form_factor", sa.String(length=50), server_default="Clamshell", nullable=False),
    )
    op.add_column("laptop_configuration", sa.Column("market_positioning", sa.String(length=50), nullable=True))
    op.add_column("laptop_configuration", sa.Column("release_year", sa.Integer(), nullable=True))
    op.add_column("laptop_configuration", sa.Column("warranty", sa.String(length=100), nullable=True))
    op.add_column("laptop_configuration", sa.Column("warranty_years", sa.Integer(), nullable=True))
    op.add_column(
        "laptop_configuration", sa.Column("is_bundle", sa.Boolean(), server_default=sa.text("false"), nullable=False)
    )

    # CPU
    op.add_column(
        "laptop_configuration",
        sa.Column("cpu_manufacturer", sa.String(length=50), nullable=False, server_default="Unknown"),
    )
    op.add_column("laptop_configuration", sa.Column("cpu_line", sa.String(length=50), nullable=True))
    op.add_column(
        "laptop_configuration", sa.Column("cpu_model", sa.String(length=100), nullable=False, server_default="Unknown")
    )
    op.add_column("laptop_configuration", sa.Column("cpu_series", sa.String(length=50), nullable=True))
    op.add_column("laptop_configuration", sa.Column("cpu_full_name", sa.String(length=120), nullable=True))
    op.add_column("laptop_configuration", sa.Column("cpu_cores", sa.Integer(), nullable=False, server_default="4"))
    op.add_column("laptop_configuration", sa.Column("cpu_threads", sa.Integer(), nullable=False, server_default="4"))
    op.add_column(
        "laptop_configuration", sa.Column("cpu_base_clock_ghz", sa.Numeric(precision=4, scale=2), nullable=True)
    )
    op.add_column(
        "laptop_configuration", sa.Column("cpu_boost_clock_ghz", sa.Numeric(precision=4, scale=2), nullable=True)
    )
    op.add_column("laptop_configuration", sa.Column("cpu_cache_mb", sa.Integer(), nullable=True))
    op.add_column("laptop_configuration", sa.Column("cpu_base_power_w", sa.Integer(), nullable=True))
    op.add_column("laptop_configuration", sa.Column("cpu_npu_tops", sa.Numeric(precision=6, scale=2), nullable=True))
    op.add_column("laptop_configuration", sa.Column("cpu_microarchitecture", sa.String(length=50), nullable=True))

    # GPU
    op.add_column(
        "laptop_configuration",
        sa.Column("gpu_manufacturer", sa.String(length=50), nullable=False, server_default="Unknown"),
    )
    op.add_column(
        "laptop_configuration",
        sa.Column("gpu_model", sa.String(length=100), nullable=False, server_default="Integrated"),
    )
    op.add_column("laptop_configuration", sa.Column("gpu_variant", sa.String(length=50), nullable=True))
    op.add_column("laptop_configuration", sa.Column("gpu_vram_gb", sa.Integer(), nullable=True))
    op.add_column("laptop_configuration", sa.Column("gpu_vram_type", sa.String(length=20), nullable=True))
    op.add_column("laptop_configuration", sa.Column("gpu_tdp_w", sa.Integer(), nullable=True))
    op.add_column(
        "laptop_configuration",
        sa.Column("gpu_integrated", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("laptop_configuration", sa.Column("gpu_ai_tops", sa.Integer(), nullable=True))
    op.add_column("laptop_configuration", sa.Column("gpu_igpu_model", sa.String(length=100), nullable=True))

    # Memory
    op.add_column(
        "laptop_configuration", sa.Column("ram_capacity_gb", sa.Integer(), nullable=False, server_default="8")
    )
    op.add_column(
        "laptop_configuration", sa.Column("ram_type", sa.String(length=20), nullable=False, server_default="DDR4")
    )
    op.add_column("laptop_configuration", sa.Column("ram_speed_mhz", sa.Integer(), nullable=True))
    op.add_column("laptop_configuration", sa.Column("ram_slot_count", sa.Integer(), nullable=True))
    op.add_column("laptop_configuration", sa.Column("ram_max_supported_gb", sa.Integer(), nullable=True))
    op.add_column(
        "laptop_configuration",
        sa.Column("ram_is_soldered", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("laptop_configuration", sa.Column("ram_channels", sa.String(length=30), nullable=True))

    # Storage
    op.add_column(
        "laptop_configuration", sa.Column("storage_capacity_gb", sa.Integer(), nullable=False, server_default="256")
    )
    op.add_column(
        "laptop_configuration", sa.Column("storage_type", sa.String(length=20), server_default="SSD", nullable=False)
    )
    op.add_column("laptop_configuration", sa.Column("storage_interface", sa.String(length=50), nullable=True))
    op.add_column("laptop_configuration", sa.Column("storage_slot_count", sa.Integer(), nullable=True))

    # Display
    op.add_column(
        "laptop_configuration",
        sa.Column("display_size_inches", sa.Numeric(precision=4, scale=1), nullable=False, server_default="15.6"),
    )
    op.add_column(
        "laptop_configuration",
        sa.Column("display_resolution", sa.String(length=30), nullable=False, server_default="1920x1080"),
    )
    op.add_column(
        "laptop_configuration", sa.Column("display_width", sa.Integer(), nullable=False, server_default="1920")
    )
    op.add_column(
        "laptop_configuration", sa.Column("display_height", sa.Integer(), nullable=False, server_default="1080")
    )
    op.add_column("laptop_configuration", sa.Column("display_panel_type", sa.String(length=30), nullable=True))
    op.add_column(
        "laptop_configuration", sa.Column("display_refresh_rate_hz", sa.Integer(), server_default="60", nullable=False)
    )
    op.add_column(
        "laptop_configuration",
        sa.Column("display_aspect_ratio", sa.String(length=20), server_default="16:9", nullable=True),
    )
    op.add_column("laptop_configuration", sa.Column("display_brightness_nits", sa.Integer(), nullable=True))
    op.add_column("laptop_configuration", sa.Column("display_color_gamut", sa.String(length=50), nullable=True))
    op.add_column(
        "laptop_configuration",
        sa.Column("display_touchscreen", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "laptop_configuration", sa.Column("display_hdr", sa.Boolean(), server_default=sa.text("false"), nullable=False)
    )

    # Power & Battery
    op.add_column(
        "laptop_configuration", sa.Column("battery_capacity_wh", sa.Numeric(precision=6, scale=2), nullable=True)
    )
    op.add_column("laptop_configuration", sa.Column("battery_cells", sa.Integer(), nullable=True))
    op.add_column("laptop_configuration", sa.Column("power_adapter_w", sa.Numeric(precision=6, scale=2), nullable=True))
    op.add_column(
        "laptop_configuration",
        sa.Column("fast_charging", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "laptop_configuration",
        sa.Column("usb_c_pd_charging", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )

    # Physical Dimensions
    op.add_column("laptop_configuration", sa.Column("weight_kg", sa.Numeric(precision=4, scale=2), nullable=True))
    op.add_column("laptop_configuration", sa.Column("width_mm", sa.Numeric(precision=6, scale=2), nullable=True))
    op.add_column("laptop_configuration", sa.Column("depth_mm", sa.Numeric(precision=6, scale=2), nullable=True))
    op.add_column("laptop_configuration", sa.Column("height_mm", sa.Numeric(precision=6, scale=2), nullable=True))

    # Build, Audio & Webcam
    op.add_column(
        "laptop_configuration",
        sa.Column("has_backlit_keyboard", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("laptop_configuration", sa.Column("keyboard_backlight_type", sa.String(length=50), nullable=True))
    op.add_column(
        "laptop_configuration",
        sa.Column("has_fingerprint", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "laptop_configuration",
        sa.Column("has_copilot_key", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "laptop_configuration",
        sa.Column("security_features", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
    )
    op.add_column("laptop_configuration", sa.Column("speaker_count", sa.Integer(), server_default="2", nullable=False))
    op.add_column("laptop_configuration", sa.Column("audio_system", sa.String(length=50), nullable=True))
    op.add_column("laptop_configuration", sa.Column("webcam_resolution", sa.String(length=30), nullable=True))
    op.add_column(
        "laptop_configuration",
        sa.Column("has_ir_camera", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "laptop_configuration",
        sa.Column("has_privacy_shutter", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )

    # Connectivity & OS
    op.add_column("laptop_configuration", sa.Column("wifi", sa.String(length=50), nullable=True))
    op.add_column("laptop_configuration", sa.Column("bluetooth", sa.String(length=50), nullable=True))
    op.add_column(
        "laptop_configuration", sa.Column("has_ethernet", sa.Boolean(), server_default=sa.text("false"), nullable=False)
    )
    op.add_column("laptop_configuration", sa.Column("ethernet_speed", sa.String(length=30), nullable=True))
    op.add_column(
        "laptop_configuration",
        sa.Column("has_card_reader", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("laptop_configuration", sa.Column("operating_system", sa.String(length=50), nullable=True))
    op.add_column(
        "laptop_configuration", sa.Column("ports", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False)
    )

    # Pricing & Stock
    op.add_column(
        "laptop_configuration", sa.Column("previous_min_price_egp", sa.Numeric(precision=12, scale=2), nullable=True)
    )
    op.add_column(
        "laptop_configuration", sa.Column("in_stock", sa.Boolean(), server_default=sa.text("true"), nullable=False)
    )
    op.add_column(
        "laptop_configuration",
        sa.Column("available_stores", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
    )

    # Lifecycle & Freshness Timestamps
    op.add_column(
        "laptop_configuration",
        sa.Column("laptop_added_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column(
        "laptop_configuration",
        sa.Column("price_updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column(
        "laptop_configuration",
        sa.Column("price_checked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 6. Create Indexes
    op.create_index("ix_laptop_configuration_mpn", "laptop_configuration", ["mpn"])
    op.create_index("ix_laptop_configuration_brand", "laptop_configuration", ["brand"])
    op.create_index("ix_laptop_configuration_laptop_family", "laptop_configuration", ["laptop_family"])
    op.create_index("ix_laptop_configuration_laptop_model", "laptop_configuration", ["laptop_model"])
    op.create_index("ix_laptop_configuration_cpu_model", "laptop_configuration", ["cpu_model"])
    op.create_index("ix_laptop_configuration_gpu_model", "laptop_configuration", ["gpu_model"])
    op.create_index("ix_laptop_configuration_ram_capacity_gb", "laptop_configuration", ["ram_capacity_gb"])
    op.create_index("ix_laptop_configuration_storage_capacity_gb", "laptop_configuration", ["storage_capacity_gb"])
    op.create_index("ix_laptop_configuration_display_size_inches", "laptop_configuration", ["display_size_inches"])
    op.create_index(
        "ix_laptop_configuration_display_refresh_rate_hz", "laptop_configuration", ["display_refresh_rate_hz"]
    )
    op.create_index("ix_laptop_configuration_weight_kg", "laptop_configuration", ["weight_kg"])
    op.create_index("ix_laptop_configuration_in_stock", "laptop_configuration", ["in_stock"])
    op.create_index("ix_laptop_configuration_laptop_added_at", "laptop_configuration", ["laptop_added_at"])
    op.create_index("ix_laptop_configuration_price_updated_at", "laptop_configuration", ["price_updated_at"])
    op.create_index("ix_laptop_configuration_price_checked_at", "laptop_configuration", ["price_checked_at"])


def downgrade() -> None:
    """Reverting this migration is not recommended in development as normalized tables are superseded."""
    pass
