using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using Users.Domain.Entities;

namespace Users.Infrastructure.Persistence.Configurations;

public sealed class RoleConfiguration : IEntityTypeConfiguration<Role>
{
    public void Configure(EntityTypeBuilder<Role> builder)
    {
        builder.ToTable("roles");

        builder.HasKey(r => r.Id);

        builder.Property(r => r.Id)
            .HasColumnName("id")
            .ValueGeneratedNever();

        builder.Property(r => r.Name)
            .HasColumnName("name")
            .HasMaxLength(32)
            .IsRequired();

        builder.Property(r => r.Description)
            .HasColumnName("description")
            .HasMaxLength(200);

        builder.Property(r => r.CreatedAtUtc)
            .HasColumnName("created_at_utc")
            .IsRequired();

        builder.Property(r => r.UpdatedAtUtc)
            .HasColumnName("updated_at_utc");

        builder.HasIndex(r => r.Name).IsUnique();

        var seededAt = new DateTime(2026, 1, 1, 0, 0, 0, DateTimeKind.Utc);
        builder.HasData(
            new
            {
                Id = Role.UserRoleId,
                Name = "User",
                Description = "Standard authenticated shopper account.",
                CreatedAtUtc = seededAt,
                UpdatedAtUtc = (DateTime?)null,
            },
            new
            {
                Id = Role.AdminRoleId,
                Name = "Admin",
                Description = "Administrative account for Users Service management.",
                CreatedAtUtc = seededAt,
                UpdatedAtUtc = (DateTime?)null,
            });
    }
}
