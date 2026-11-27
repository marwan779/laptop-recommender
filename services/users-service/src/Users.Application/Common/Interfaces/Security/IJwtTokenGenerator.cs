using Users.Domain.Entities;

namespace Users.Application.Common.Interfaces.Security;

public interface IJwtTokenGenerator
{
    int RefreshTokenExpiryDays { get; }
    string GenerateAccessToken(User user, string roleName);
    string GenerateRefreshToken();
    string HashToken(string rawToken);
}
