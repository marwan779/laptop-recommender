using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using Users.Domain.Entities;

namespace Users.Infrastructure.Persistence.Configurations;

public sealed class FeedbackReportConfiguration : IEntityTypeConfiguration<FeedbackReport>
{
    public void Configure(EntityTypeBuilder<FeedbackReport> builder)
    {
        builder.ToTable("feedback_reports");

        builder.HasKey(f => f.Id);

        builder.Property(f => f.Id)
            .HasColumnName("id")
            .ValueGeneratedNever();

        builder.Property(f => f.UserId)
            .HasColumnName("user_id");

        builder.Property(f => f.ReporterEmail)
            .HasColumnName("reporter_email")
            .HasMaxLength(256);

        builder.Property(f => f.Category)
            .HasColumnName("category")
            .HasMaxLength(40)
            .IsRequired();

        builder.Property(f => f.CanonicalId)
            .HasColumnName("canonical_id")
            .HasMaxLength(160);

        builder.Property(f => f.LaptopTitleSnapshot)
            .HasColumnName("laptop_title_snapshot")
            .HasMaxLength(300);

        builder.Property(f => f.Title)
            .HasColumnName("title")
            .HasMaxLength(200)
            .IsRequired();

        builder.Property(f => f.Description)
            .HasColumnName("description")
            .HasMaxLength(2000)
            .IsRequired();

        builder.Property(f => f.PageUrl)
            .HasColumnName("page_url")
            .HasMaxLength(500);

        builder.Property(f => f.Status)
            .HasColumnName("status")
            .HasMaxLength(30)
            .HasDefaultValue(FeedbackStatuses.Open)
            .IsRequired();

        builder.Property(f => f.AdminNotes)
            .HasColumnName("admin_notes")
            .HasMaxLength(1000);

        builder.Property(f => f.ResolvedByUserId)
            .HasColumnName("resolved_by_user_id");

        builder.Property(f => f.ResolvedAtUtc)
            .HasColumnName("resolved_at_utc");

        builder.Property(f => f.CreatedAtUtc)
            .HasColumnName("created_at_utc")
            .IsRequired();

        builder.Property(f => f.UpdatedAtUtc)
            .HasColumnName("updated_at_utc");

        builder.HasIndex(f => new { f.Status, f.CreatedAtUtc });
        builder.HasIndex(f => new { f.UserId, f.CreatedAtUtc });
        builder.HasIndex(f => f.CanonicalId);

        builder.HasOne(f => f.User)
            .WithMany()
            .HasForeignKey(f => f.UserId)
            .OnDelete(DeleteBehavior.SetNull);
    }
}
