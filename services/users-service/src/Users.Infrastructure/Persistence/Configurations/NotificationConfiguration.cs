using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using Users.Domain.Entities;

namespace Users.Infrastructure.Persistence.Configurations;

public sealed class NotificationConfiguration : IEntityTypeConfiguration<Notification>
{
    public void Configure(EntityTypeBuilder<Notification> builder)
    {
        builder.ToTable("notifications");

        builder.HasKey(n => n.Id);

        builder.Property(n => n.Id)
            .HasColumnName("id")
            .ValueGeneratedNever();

        builder.Property(n => n.UserId)
            .HasColumnName("user_id")
            .IsRequired();

        builder.Property(n => n.CanonicalId)
            .HasColumnName("canonical_id")
            .HasMaxLength(160)
            .IsRequired();

        builder.Property(n => n.Title)
            .HasColumnName("title")
            .HasMaxLength(300)
            .IsRequired();

        builder.Property(n => n.Message)
            .HasColumnName("message")
            .HasMaxLength(1000)
            .IsRequired();

        builder.Property(n => n.ChangeType)
            .HasColumnName("change_type")
            .HasMaxLength(50)
            .IsRequired();

        builder.Property(n => n.OldPriceEgp)
            .HasColumnName("old_price_egp")
            .HasColumnType("numeric(12,2)");

        builder.Property(n => n.NewPriceEgp)
            .HasColumnName("new_price_egp")
            .HasColumnType("numeric(12,2)");

        builder.Property(n => n.CheapestStore)
            .HasColumnName("cheapest_store")
            .HasMaxLength(120);

        builder.Property(n => n.IsRead)
            .HasColumnName("is_read")
            .HasDefaultValue(false)
            .IsRequired();

        builder.Property(n => n.ReadAtUtc)
            .HasColumnName("read_at_utc");

        builder.Property(n => n.CreatedAtUtc)
            .HasColumnName("created_at_utc")
            .IsRequired();

        builder.Property(n => n.UpdatedAtUtc)
            .HasColumnName("updated_at_utc");

        builder.HasIndex(n => new { n.UserId, n.IsRead, n.CreatedAtUtc });
        builder.HasIndex(n => n.CanonicalId);

        builder.HasOne(n => n.User)
            .WithMany()
            .HasForeignKey(n => n.UserId)
            .OnDelete(DeleteBehavior.Cascade);
    }
}
