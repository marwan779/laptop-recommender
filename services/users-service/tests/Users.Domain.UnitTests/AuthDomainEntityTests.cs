using Users.Domain.Common;
using Users.Domain.Entities;

namespace Users.Domain.UnitTests;

public sealed class AuthDomainEntityTests
{
    [Fact]
    public void RoleCreate_RejectsBlankName()
    {
        Assert.Throws<DomainException>(() => Role.Create("   "));
    }

    [Fact]
    public void UserCreate_NormalizesEmailAndDefaultsToUserRole()
    {
        var user = User.Create("  Alice@Example.COM ", "Alice Doe", "hashed-secret", preferredLanguage: "EN");

        Assert.Equal("alice@example.com", user.Email);
        Assert.Equal("Alice Doe", user.FullName);
        Assert.Equal(Role.UserRoleId, user.RoleId);
        Assert.Equal("en", user.PreferredLanguage);
        Assert.True(user.IsActive);
        Assert.False(user.EmailVerified);
    }

    [Fact]
    public void UserCreate_RejectsInvalidEmail()
    {
        Assert.Throws<DomainException>(() => User.Create("not-an-email", "Alice", "hash"));
    }

    [Fact]
    public void RefreshToken_TracksExpiryAndRevocation()
    {
        var now = new DateTime(2026, 11, 26, 18, 0, 0, DateTimeKind.Utc);
        var token = RefreshToken.Create(Guid.NewGuid(), "hash-1", now.AddDays(7));

        Assert.True(token.IsActive(now));
        Assert.False(token.IsExpired(now));

        token.Revoke(now.AddMinutes(5), "hash-2");

        Assert.False(token.IsActive(now.AddMinutes(6)));
        Assert.Equal("hash-2", token.ReplacedByTokenHash);
    }
}
