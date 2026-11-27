using Users.Domain.Common;

namespace Users.Domain.Entities;

public sealed class User : BaseEntity
{
    public string Email { get; private set; } = string.Empty;
    public string FullName { get; private set; } = string.Empty;
    public string PasswordHash { get; private set; } = string.Empty;
    public Guid RoleId { get; private set; }
    public Role? Role { get; private set; }
    public string PreferredLanguage { get; private set; } = "ar";
    public bool IsActive { get; private set; } = true;
    public bool EmailVerified { get; private set; }

    private readonly List<RefreshToken> _refreshTokens = [];
    public IReadOnlyCollection<RefreshToken> RefreshTokens => _refreshTokens.AsReadOnly();

    private User() { }

    private User(
        string email,
        string fullName,
        string passwordHash,
        Guid roleId,
        string preferredLanguage)
    {
        Email = email;
        FullName = fullName;
        PasswordHash = passwordHash;
        RoleId = roleId;
        PreferredLanguage = preferredLanguage;
        IsActive = true;
        EmailVerified = false;
    }

    public static User Create(
        string email,
        string fullName,
        string passwordHash,
        Guid? roleId = null,
        string preferredLanguage = "ar")
    {
        var normalizedEmail = (email ?? string.Empty).Trim().ToLowerInvariant();
        if (string.IsNullOrWhiteSpace(normalizedEmail) || !normalizedEmail.Contains('@'))
        {
            throw new DomainException("A valid email address is required.");
        }

        var trimmedName = (fullName ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(trimmedName))
        {
            throw new DomainException("Full name is required.");
        }

        if (string.IsNullOrWhiteSpace(passwordHash))
        {
            throw new DomainException("Password hash is required.");
        }

        var lang = preferredLanguage?.Trim().ToLowerInvariant() == "en" ? "en" : "ar";

        return new User(
            normalizedEmail,
            trimmedName,
            passwordHash,
            roleId ?? Role.UserRoleId,
            lang);
    }

    public void UpdateProfile(string fullName, string preferredLanguage, DateTime utcNow)
    {
        var trimmedName = (fullName ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(trimmedName))
        {
            throw new DomainException("Full name cannot be empty.");
        }

        FullName = trimmedName;
        PreferredLanguage = preferredLanguage?.Trim().ToLowerInvariant() == "en" ? "en" : "ar";
        TouchUpdatedAt(utcNow);
    }

    public void VerifyEmail(DateTime utcNow)
    {
        EmailVerified = true;
        TouchUpdatedAt(utcNow);
    }

    public void Deactivate(DateTime utcNow)
    {
        IsActive = false;
        TouchUpdatedAt(utcNow);
    }

    public void Activate(DateTime utcNow)
    {
        IsActive = true;
        TouchUpdatedAt(utcNow);
    }

    public void ChangeRole(Guid roleId, DateTime utcNow)
    {
        if (roleId == Guid.Empty)
        {
            throw new DomainException("RoleId is required.");
        }

        if (RoleId != roleId)
        {
            RoleId = roleId;
            Role = null;
        }

        TouchUpdatedAt(utcNow);
    }
}
