namespace Users.Infrastructure.Security;

public sealed class JwtSettings
{
    public const string SectionName = "Jwt";

    public string Issuer { get; init; } = "laptop-recommender-users";
    public string Audience { get; init; } = "laptop-recommender-clients";
    public string SecretKey { get; init; } = string.Empty;
    public int AccessTokenExpiryMinutes { get; init; } = 30;
    public int RefreshTokenExpiryDays { get; init; } = 7;
}
