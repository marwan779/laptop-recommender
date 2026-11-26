using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using System.Security.Cryptography;
using System.Text;
using Microsoft.Extensions.Options;
using Microsoft.IdentityModel.Tokens;
using Users.Application.Common.Interfaces;
using Users.Application.Common.Interfaces.Security;
using Users.Domain.Entities;

namespace Users.Infrastructure.Security;

public sealed class JwtTokenGenerator(
    IOptions<JwtSettings> jwtOptions,
    IDateTimeProvider dateTimeProvider) : IJwtTokenGenerator
{
    private readonly JwtSettings _settings = jwtOptions.Value;

    public int RefreshTokenExpiryDays => _settings.RefreshTokenExpiryDays;

    public string GenerateAccessToken(User user, string roleName)
    {
        if (string.IsNullOrWhiteSpace(_settings.SecretKey) || _settings.SecretKey.Length < 32)
        {
            throw new InvalidOperationException(
                "Jwt:SecretKey must be configured with at least 32 characters.");
        }

        var key = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(_settings.SecretKey));
        var credentials = new SigningCredentials(key, SecurityAlgorithms.HmacSha256);

        var claims = new List<Claim>
        {
            new(JwtRegisteredClaimNames.Sub, user.Id.ToString()),
            new(ClaimTypes.NameIdentifier, user.Id.ToString()),
            new(JwtRegisteredClaimNames.Email, user.Email),
            new(ClaimTypes.Name, user.FullName),
            new(ClaimTypes.Role, roleName),
            new("lang", user.PreferredLanguage),
            new(JwtRegisteredClaimNames.Jti, Guid.NewGuid().ToString()),
        };

        var now = dateTimeProvider.UtcNow;
        var token = new JwtSecurityToken(
            issuer: _settings.Issuer,
            audience: _settings.Audience,
            claims: claims,
            notBefore: now,
            expires: now.AddMinutes(_settings.AccessTokenExpiryMinutes),
            signingCredentials: credentials);

        return new JwtSecurityTokenHandler().WriteToken(token);
    }

    public string GenerateRefreshToken()
    {
        var bytes = RandomNumberGenerator.GetBytes(64);
        return Convert.ToBase64String(bytes);
    }

    public string HashToken(string rawToken)
    {
        var bytes = SHA256.HashData(Encoding.UTF8.GetBytes(rawToken));
        return Convert.ToHexStringLower(bytes);
    }
}
