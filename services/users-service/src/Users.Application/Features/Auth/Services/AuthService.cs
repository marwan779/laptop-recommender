using Users.Application.Common.Interfaces;
using Users.Application.Common.Interfaces.Repositories;
using Users.Application.Common.Interfaces.Security;
using Users.Application.Common.Models;
using Users.Application.Features.Auth.DTOs;
using Users.Domain.Common;
using Users.Domain.Entities;

namespace Users.Application.Features.Auth.Services;

public sealed class AuthService(
    IUserRepository userRepository,
    IRoleRepository roleRepository,
    IRefreshTokenRepository refreshTokenRepository,
    IPasswordHasher passwordHasher,
    IJwtTokenGenerator jwtTokenGenerator,
    IDateTimeProvider dateTimeProvider,
    IUnitOfWork unitOfWork) : IAuthService
{
    private const int MinPasswordLength = 8;

    public async Task<Result<AuthResponse>> RegisterAsync(
        RegisterRequest request,
        CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(request.Password) || request.Password.Length < MinPasswordLength)
        {
            return Result<AuthResponse>.Validation($"Password must be at least {MinPasswordLength} characters.");
        }

        var normalizedEmail = (request.Email ?? string.Empty).Trim().ToLowerInvariant();
        if (await userRepository.ExistsByEmailAsync(normalizedEmail, cancellationToken))
        {
            return Result<AuthResponse>.Conflict("An account with this email already exists.");
        }

        var defaultRole = await roleRepository.GetByIdAsync(Role.UserRoleId, cancellationToken);
        var roleName = defaultRole?.Name ?? "User";
        var roleId = defaultRole?.Id ?? Role.UserRoleId;

        User user;
        try
        {
            var passwordHash = passwordHasher.Hash(request.Password);
            user = User.Create(
                normalizedEmail,
                request.FullName,
                passwordHash,
                roleId,
                request.PreferredLanguage);
        }
        catch (DomainException ex)
        {
            return Result<AuthResponse>.Validation(ex.Message);
        }

        var (accessToken, rawRefreshToken, refreshTokenEntity) = IssueTokens(user, roleName);

        await userRepository.AddAsync(user, cancellationToken);
        await refreshTokenRepository.AddAsync(refreshTokenEntity, cancellationToken);
        await unitOfWork.SaveChangesAsync(cancellationToken);

        return Result<AuthResponse>.Success(
            ToAuthResponse(user, roleName, accessToken, rawRefreshToken));
    }

    public async Task<Result<AuthResponse>> LoginAsync(
        LoginRequest request,
        CancellationToken cancellationToken = default)
    {
        var normalizedEmail = (request.Email ?? string.Empty).Trim().ToLowerInvariant();
        if (string.IsNullOrWhiteSpace(normalizedEmail) || string.IsNullOrEmpty(request.Password))
        {
            return Result<AuthResponse>.Unauthorized("Invalid email or password.");
        }

        var user = await userRepository.GetByEmailWithRoleAsync(normalizedEmail, cancellationToken);
        if (user is null || !passwordHasher.Verify(user.PasswordHash, request.Password))
        {
            return Result<AuthResponse>.Unauthorized("Invalid email or password.");
        }

        if (!user.IsActive)
        {
            return Result<AuthResponse>.Forbidden("This account has been deactivated.");
        }

        var roleName = user.Role?.Name ?? "User";
        var (accessToken, rawRefreshToken, refreshTokenEntity) = IssueTokens(user, roleName);

        await refreshTokenRepository.AddAsync(refreshTokenEntity, cancellationToken);
        await unitOfWork.SaveChangesAsync(cancellationToken);

        return Result<AuthResponse>.Success(
            ToAuthResponse(user, roleName, accessToken, rawRefreshToken));
    }

    public async Task<Result<AuthResponse>> RefreshAsync(
        RefreshTokenRequest request,
        CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(request.RefreshToken))
        {
            return Result<AuthResponse>.Unauthorized("Refresh token is required.");
        }

        var now = dateTimeProvider.UtcNow;
        var tokenHash = jwtTokenGenerator.HashToken(request.RefreshToken.Trim());
        var existingToken = await refreshTokenRepository.GetByTokenHashAsync(tokenHash, cancellationToken);

        if (existingToken is null || existingToken.User is null)
        {
            return Result<AuthResponse>.Unauthorized("Invalid refresh token.");
        }

        // Token reuse detection: revoked token presented again -> revoke all active sessions.
        if (existingToken.RevokedAtUtc is not null)
        {
            await refreshTokenRepository.RevokeAllForUserAsync(existingToken.UserId, now, cancellationToken);
            return Result<AuthResponse>.Unauthorized("Refresh token has already been used or revoked.");
        }

        if (existingToken.IsExpired(now))
        {
            return Result<AuthResponse>.Unauthorized("Refresh token has expired.");
        }

        var user = existingToken.User;
        if (!user.IsActive)
        {
            return Result<AuthResponse>.Forbidden("This account has been deactivated.");
        }

        var roleName = user.Role?.Name ?? "User";
        var (accessToken, rawNewRefreshToken, newRefreshTokenEntity) = IssueTokens(user, roleName);

        existingToken.Revoke(now, newRefreshTokenEntity.TokenHash);
        await refreshTokenRepository.AddAsync(newRefreshTokenEntity, cancellationToken);
        await unitOfWork.SaveChangesAsync(cancellationToken);

        return Result<AuthResponse>.Success(
            ToAuthResponse(user, roleName, accessToken, rawNewRefreshToken));
    }

    public async Task<Result> LogoutAsync(
        RefreshTokenRequest request,
        CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(request.RefreshToken))
        {
            return Result.Success();
        }

        var tokenHash = jwtTokenGenerator.HashToken(request.RefreshToken.Trim());
        var existingToken = await refreshTokenRepository.GetByTokenHashAsync(tokenHash, cancellationToken);
        if (existingToken is null)
        {
            return Result.Success();
        }

        existingToken.Revoke(dateTimeProvider.UtcNow);
        await unitOfWork.SaveChangesAsync(cancellationToken);
        return Result.Success();
    }

    public async Task<Result<UserProfileResponse>> GetProfileAsync(
        Guid userId,
        CancellationToken cancellationToken = default)
    {
        var user = await userRepository.GetByIdWithRoleAsync(userId, cancellationToken);
        if (user is null)
        {
            return Result<UserProfileResponse>.NotFound("User not found.");
        }

        return Result<UserProfileResponse>.Success(new UserProfileResponse(
            user.Id,
            user.Email,
            user.FullName,
            user.Role?.Name ?? "User",
            user.PreferredLanguage,
            user.EmailVerified));
    }

    private (string AccessToken, string RawRefreshToken, RefreshToken Entity) IssueTokens(
        User user,
        string roleName)
    {
        var now = dateTimeProvider.UtcNow;
        var accessToken = jwtTokenGenerator.GenerateAccessToken(user, roleName);
        var rawRefreshToken = jwtTokenGenerator.GenerateRefreshToken();
        var refreshTokenHash = jwtTokenGenerator.HashToken(rawRefreshToken);
        var expiresAt = now.AddDays(jwtTokenGenerator.RefreshTokenExpiryDays);

        var entity = RefreshToken.Create(user.Id, refreshTokenHash, expiresAt);
        return (accessToken, rawRefreshToken, entity);
    }

    private static AuthResponse ToAuthResponse(
        User user,
        string roleName,
        string accessToken,
        string rawRefreshToken) =>
        new(
            accessToken,
            rawRefreshToken,
            user.Id,
            user.Email,
            user.FullName,
            roleName,
            user.PreferredLanguage);
}
