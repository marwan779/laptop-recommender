using Users.Domain.Common;

namespace Users.Domain.Entities;

public sealed class RefreshToken : BaseEntity
{
    public Guid UserId { get; private set; }
    public User? User { get; private set; }
    public string TokenHash { get; private set; } = string.Empty;
    public DateTime ExpiresAtUtc { get; private set; }
    public DateTime? RevokedAtUtc { get; private set; }
    public string? ReplacedByTokenHash { get; private set; }

    private RefreshToken() { }

    private RefreshToken(Guid userId, string tokenHash, DateTime expiresAtUtc)
    {
        UserId = userId;
        TokenHash = tokenHash;
        ExpiresAtUtc = expiresAtUtc;
    }

    public static RefreshToken Create(Guid userId, string tokenHash, DateTime expiresAtUtc)
    {
        if (userId == Guid.Empty)
        {
            throw new DomainException("UserId is required for a refresh token.");
        }

        if (string.IsNullOrWhiteSpace(tokenHash))
        {
            throw new DomainException("TokenHash cannot be empty.");
        }

        return new RefreshToken(userId, tokenHash.Trim(), expiresAtUtc);
    }

    public bool IsExpired(DateTime utcNow) => utcNow >= ExpiresAtUtc;

    public bool IsActive(DateTime utcNow) => RevokedAtUtc is null && !IsExpired(utcNow);

    public void Revoke(DateTime utcNow, string? replacedByTokenHash = null)
    {
        if (RevokedAtUtc is not null)
        {
            return;
        }

        RevokedAtUtc = utcNow;
        ReplacedByTokenHash = replacedByTokenHash;
        TouchUpdatedAt(utcNow);
    }
}
