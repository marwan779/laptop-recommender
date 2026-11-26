using Microsoft.AspNetCore.Identity;
using Users.Application.Common.Interfaces.Security;
using Users.Domain.Entities;

namespace Users.Infrastructure.Security;

public sealed class PasswordHasher : IPasswordHasher
{
    private readonly PasswordHasher<User> _hasher = new();

    public string Hash(string password)
    {
        return _hasher.HashPassword(null!, password);
    }

    public bool Verify(string passwordHash, string providedPassword)
    {
        var result = _hasher.VerifyHashedPassword(null!, passwordHash, providedPassword);
        return result is PasswordVerificationResult.Success
            or PasswordVerificationResult.SuccessRehashNeeded;
    }
}
