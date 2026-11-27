using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using Users.Domain.Entities;

namespace Users.Infrastructure.Persistence.Configurations;

public sealed class WishlistItemConfiguration : IEntityTypeConfiguration<WishlistItem>
{
    public void Configure(EntityTypeBuilder<WishlistItem> builder)
    {
        builder.ToTable("wishlist_items");

        builder.HasKey(w => w.Id);

        builder.Property(w => w.Id)
            .HasColumnName("id")
            .ValueGeneratedNever();

        builder.Property(w => w.UserId)
            .HasColumnName("user_id")
            .IsRequired();

        builder.Property(w => w.CanonicalId)
            .HasColumnName("canonical_id")
            .HasMaxLength(160)
            .IsRequired();

        builder.Property(w => w.TitleSnapshot)
            .HasColumnName("title_snapshot")
            .HasMaxLength(300)
            .IsRequired();

        builder.Property(w => w.ThumbnailUrlSnapshot)
            .HasColumnName("thumbnail_url_snapshot");

        builder.Property(w => w.AddedPriceEgp)
            .HasColumnName("added_price_egp")
            .HasColumnType("numeric(12,2)")
            .IsRequired();

        builder.Property(w => w.LastNotifiedPriceEgp)
            .HasColumnName("last_notified_price_egp")
            .HasColumnType("numeric(12,2)");

        builder.Property(w => w.TargetPriceEgp)
            .HasColumnName("target_price_egp")
            .HasColumnType("numeric(12,2)");

        builder.Property(w => w.NotifyOnPriceDrop)
            .HasColumnName("notify_on_price_drop")
            .HasDefaultValue(true)
            .IsRequired();

        builder.Property(w => w.NotifyOnAnyChange)
            .HasColumnName("notify_on_any_change")
            .HasDefaultValue(false)
            .IsRequired();

        builder.Property(w => w.NotifyOnRestock)
            .HasColumnName("notify_on_restock")
            .HasDefaultValue(true)
            .IsRequired();

        builder.Property(w => w.CreatedAtUtc)
            .HasColumnName("created_at_utc")
            .IsRequired();

        builder.Property(w => w.UpdatedAtUtc)
            .HasColumnName("updated_at_utc");

        builder.HasIndex(w => new { w.UserId, w.CanonicalId }).IsUnique();
        builder.HasIndex(w => w.CanonicalId);

        builder.HasOne(w => w.User)
            .WithMany()
            .HasForeignKey(w => w.UserId)
            .OnDelete(DeleteBehavior.Cascade);
    }
}
