using Users.Application.Common.Interfaces;
using Users.Application.Common.Interfaces.Repositories;
using Users.Application.Common.Interfaces.Security;
using Users.Application.Common.Models;
using Users.Application.Features.Auth.DTOs;
using Users.Application.Features.Auth.Services;
using Users.Domain.Entities;

namespace Users.Application.UnitTests.Features.Auth;

public sealed class AuthServiceTests
{
    private readonly FakeUserRepository _users = new();
    private readonly FakeRoleRepository _roles = new();
    private readonly FakeRefreshTokenRepository _tokens;
    private readonly FakePasswordHasher _hasher = new();
    private readonly FakeJwtTokenGenerator _jwt = new();
    private readonly FakeClock _clock = new(new DateTime(2026, 11, 26, 19, 0, 0, DateTimeKind.Utc));
    private readonly FakeUnitOfWork _uow = new();
    private readonly AuthService _sut;

    public AuthServiceTests()
    {
        _tokens = new FakeRefreshTokenRepository(_users);
        _sut = new AuthService(_users, _roles, _tokens, _hasher, _jwt, _clock, _uow);
    }

    [Fact]
    public async Task RegisterAsync_CreatesUserAndIssuesTokens()
    {
        var result = await _sut.RegisterAsync(
            new RegisterRequest("  Alice@Example.com ", "Alice Doe", "StrongPass123!", "en"));

        Assert.True(result.IsSuccess);
        Assert.NotNull(result.Value);
        Assert.Equal("alice@example.com", result.Value!.Email);
        Assert.Equal("User", result.Value.Role);
        Assert.Equal("en", result.Value.PreferredLanguage);
        Assert.Equal(1, _uow.SaveCount);
        Assert.Single(_users.Items);
        Assert.Single(_tokens.Items);
    }

    [Fact]
    public async Task RegisterAsync_DuplicateEmail_ReturnsConflict()
    {
        await _sut.RegisterAsync(new RegisterRequest("alice@example.com", "Alice", "StrongPass123!"));

        var duplicate = await _sut.RegisterAsync(new RegisterRequest("ALICE@example.com", "Alice 2", "StrongPass123!"));

        Assert.True(duplicate.IsFailure);
        Assert.Equal(ErrorType.Conflict, duplicate.ErrorType);
    }

    [Fact]
    public async Task RegisterAsync_ShortPassword_ReturnsValidation()
    {
        var result = await _sut.RegisterAsync(new RegisterRequest("alice@example.com", "Alice", "short"));

        Assert.True(result.IsFailure);
        Assert.Equal(ErrorType.Validation, result.ErrorType);
    }

    [Fact]
    public async Task LoginAsync_ValidCredentials_ReturnsTokens()
    {
        await _sut.RegisterAsync(new RegisterRequest("bob@example.com", "Bob", "Secret1234"));

        var result = await _sut.LoginAsync(new LoginRequest("BOB@example.com", "Secret1234"));

        Assert.True(result.IsSuccess);
        Assert.Equal("bob@example.com", result.Value!.Email);
        Assert.Equal(2, _tokens.Items.Count);
    }

    [Fact]
    public async Task LoginAsync_WrongPassword_ReturnsUnauthorized()
    {
        await _sut.RegisterAsync(new RegisterRequest("bob@example.com", "Bob", "Secret1234"));

        var result = await _sut.LoginAsync(new LoginRequest("bob@example.com", "WrongPass"));

        Assert.True(result.IsFailure);
        Assert.Equal(ErrorType.Unauthorized, result.ErrorType);
    }

    [Fact]
    public async Task LoginAsync_DeactivatedUser_ReturnsForbidden()
    {
        var reg = await _sut.RegisterAsync(new RegisterRequest("bob@example.com", "Bob", "Secret1234"));
        _users.Items.Single(u => u.Id == reg.Value!.UserId).Deactivate(_clock.UtcNow);

        var result = await _sut.LoginAsync(new LoginRequest("bob@example.com", "Secret1234"));

        Assert.True(result.IsFailure);
        Assert.Equal(ErrorType.Forbidden, result.ErrorType);
    }

    [Fact]
    public async Task RefreshAsync_ValidToken_RotatesToken()
    {
        var reg = await _sut.RegisterAsync(new RegisterRequest("carol@example.com", "Carol", "Secret1234"));
        var oldRefresh = reg.Value!.RefreshToken;

        _clock.UtcNow = _clock.UtcNow.AddHours(1);
        var refreshed = await _sut.RefreshAsync(new RefreshTokenRequest(oldRefresh));

        Assert.True(refreshed.IsSuccess);
        Assert.NotEqual(oldRefresh, refreshed.Value!.RefreshToken);
        Assert.Equal(2, _tokens.Items.Count);
        Assert.NotNull(_tokens.Items[0].RevokedAtUtc);
        Assert.True(_tokens.Items[1].IsActive(_clock.UtcNow));
    }

    [Fact]
    public async Task RefreshAsync_ReusedRevokedToken_RevokesAllUserTokens()
    {
        var reg = await _sut.RegisterAsync(new RegisterRequest("carol@example.com", "Carol", "Secret1234"));
        var stolenOldToken = reg.Value!.RefreshToken;
        await _sut.RefreshAsync(new RefreshTokenRequest(stolenOldToken));

        var reuseAttempt = await _sut.RefreshAsync(new RefreshTokenRequest(stolenOldToken));

        Assert.True(reuseAttempt.IsFailure);
        Assert.Equal(ErrorType.Unauthorized, reuseAttempt.ErrorType);
        Assert.All(_tokens.Items, t => Assert.NotNull(t.RevokedAtUtc));
    }

    [Fact]
    public async Task LogoutAsync_RevokesProvidedToken()
    {
        var reg = await _sut.RegisterAsync(new RegisterRequest("dave@example.com", "Dave", "Secret1234"));

        var logout = await _sut.LogoutAsync(new RefreshTokenRequest(reg.Value!.RefreshToken));

        Assert.True(logout.IsSuccess);
        Assert.NotNull(_tokens.Items.Single().RevokedAtUtc);
    }

    [Fact]
    public async Task GetProfileAsync_ReturnsProfileOrNotFound()
    {
        var reg = await _sut.RegisterAsync(new RegisterRequest("eve@example.com", "Eve", "Secret1234", "ar"));

        var found = await _sut.GetProfileAsync(reg.Value!.UserId);
        var missing = await _sut.GetProfileAsync(Guid.NewGuid());

        Assert.True(found.IsSuccess);
        Assert.Equal("eve@example.com", found.Value!.Email);
        Assert.True(missing.IsFailure);
        Assert.Equal(ErrorType.NotFound, missing.ErrorType);
    }

    private sealed class FakeUserRepository : IUserRepository
    {
        public List<User> Items { get; } = [];

        public Task<User?> GetByIdWithRoleAsync(Guid id, CancellationToken cancellationToken = default) =>
            Task.FromResult(Items.FirstOrDefault(u => u.Id == id));

        public Task<User?> GetByEmailWithRoleAsync(string normalizedEmail, CancellationToken cancellationToken = default) =>
            Task.FromResult(Items.FirstOrDefault(u => u.Email == normalizedEmail));

        public Task<bool> ExistsByEmailAsync(string normalizedEmail, CancellationToken cancellationToken = default) =>
            Task.FromResult(Items.Any(u => u.Email == normalizedEmail));

        public Task AddAsync(User user, CancellationToken cancellationToken = default)
        {
            Items.Add(user);
            return Task.CompletedTask;
        }
    }

    private sealed class FakeRoleRepository : IRoleRepository
    {
        private readonly List<Role> _roles =
        [
            Role.Create("User", "Standard user", Role.UserRoleId),
            Role.Create("Admin", "Admin user", Role.AdminRoleId),
        ];

        public Task<Role?> GetByIdAsync(Guid id, CancellationToken cancellationToken = default) =>
            Task.FromResult(_roles.FirstOrDefault(r => r.Id == id));

        public Task<Role?> GetByNameAsync(string name, CancellationToken cancellationToken = default) =>
            Task.FromResult(_roles.FirstOrDefault(r => r.Name == name));
    }

    private sealed class FakeRefreshTokenRepository(FakeUserRepository? users = null) : IRefreshTokenRepository
    {
        private readonly FakeUserRepository? _users = users;
        public List<RefreshToken> Items { get; } = [];

        public Task<RefreshToken?> GetByTokenHashAsync(string tokenHash, CancellationToken cancellationToken = default)
        {
            var token = Items.FirstOrDefault(t => t.TokenHash == tokenHash);
            if (token is not null && token.User is null && _users is not null)
            {
                var user = _users.Items.FirstOrDefault(u => u.Id == token.UserId);
                typeof(RefreshToken).GetProperty(nameof(RefreshToken.User))!.SetValue(token, user);
            }
            return Task.FromResult(token);
        }

        public Task AddAsync(RefreshToken refreshToken, CancellationToken cancellationToken = default)
        {
            Items.Add(refreshToken);
            return Task.CompletedTask;
        }

        public Task RevokeAllForUserAsync(Guid userId, DateTime utcNow, CancellationToken cancellationToken = default)
        {
            foreach (var token in Items.Where(t => t.UserId == userId && t.RevokedAtUtc is null))
            {
                token.Revoke(utcNow);
            }
            return Task.CompletedTask;
        }
    }

    private sealed class FakePasswordHasher : IPasswordHasher
    {
        public string Hash(string password) => $"HASH::{password}";
        public bool Verify(string passwordHash, string providedPassword) => passwordHash == $"HASH::{providedPassword}";
    }

    private sealed class FakeJwtTokenGenerator : IJwtTokenGenerator
    {
        private int _counter;
        public int RefreshTokenExpiryDays => 7;
        public string GenerateAccessToken(User user, string roleName) => $"jwt-{user.Id}-{roleName}";
        public string GenerateRefreshToken() => $"refresh-{++_counter}";
        public string HashToken(string rawToken) => $"sha256-{rawToken}";
    }

    private sealed class FakeClock(DateTime initialUtc) : IDateTimeProvider
    {
        public DateTime UtcNow { get; set; } = initialUtc;
    }

    private sealed class FakeUnitOfWork : IUnitOfWork
    {
        public int SaveCount { get; private set; }
        public Task<int> SaveChangesAsync(CancellationToken cancellationToken = default)
        {
            SaveCount++;
            return Task.FromResult(1);
        }
    }
}
