using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using Users.Domain.Entities;

namespace Users.Infrastructure.Persistence.Configurations;

public sealed class InboxMessageConfiguration : IEntityTypeConfiguration<InboxMessage>
{
    public void Configure(EntityTypeBuilder<InboxMessage> builder)
    {
        builder.ToTable("inbox_messages");

        builder.HasKey(m => m.MessageId);

        builder.Property(m => m.MessageId)
            .HasColumnName("message_id")
            .HasMaxLength(128)
            .ValueGeneratedNever();

        builder.Property(m => m.RoutingKey)
            .HasColumnName("routing_key")
            .HasMaxLength(128)
            .IsRequired();

        builder.Property(m => m.ProcessedAtUtc)
            .HasColumnName("processed_at_utc")
            .IsRequired();

        builder.HasIndex(m => m.ProcessedAtUtc);
    }
}
