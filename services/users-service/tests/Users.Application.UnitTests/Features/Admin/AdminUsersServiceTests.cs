using Users.Application.Common.Interfaces;
using Users.Application.Common.Interfaces.Caching;
using Users.Application.Common.Interfaces.Repositories;
using Users.Application.Common.Models;
using Users.Application.Features.Admin.DTOs;
using Users.Application.Features.Admin.Services;
using Users.Domain.Entities;

namespace Users.Application.UnitTests.Features.Admin;

public sealed class AdminUsersServiceTests
{
    private readonly FakeUserRepo _userRepo = new();
    private readonly FakeRoleRepo _roleRepo = new();
    private readonly FakeUnitOfWork _uow = new();
    private readonly FakeClock _clock = new(new DateTime(2026, 11, 27, 8, 0, 0, DateTimeKind.Utc));
    private readonly FakeCache _cache = new();
    private readonly AdminUsersService _sut;

    public AdminUsersServiceTests()
    {
        _sut = new AdminUsersService(_userRepo, _roleRepo, _uow, _clock, _cache);
    }

    [Fact]
    public async Task ChangeUserRoleAsync_PromotesUserToAdmin_AndEvictsProfileCache()
    {
        var admin = User.Create("admin@example.com", "Admin", "hash", Role.AdminRoleId);
        var shopper = User.Create("user@example.com", "Shopper", "hash", Role.UserRoleId);
        _userRepo.Users.AddRange([admin, shopper]);

        var result = await _sut.ChangeUserRoleAsync(admin.Id, shopper.Id, new ChangeUserRoleRequest("Admin"));

        Assert.True(result.IsSuccess);
        Assert.Equal("Admin", result.Value!.Role);
        Assert.Equal(Role.AdminRoleId, shopper.RoleId);
        Assert.Equal(1, _uow.SaveCount);
        Assert.Contains($"users:{shopper.Id}:profile:", _cache.ClearedPrefixes);
    }

    [Fact]
    public async Task ChangeUserRoleAsync_DemotingSelf_ReturnsValidationError()
    {
        var admin = User.Create("admin@example.com", "Admin", "hash", Role.AdminRoleId);
        _userRepo.Users.Add(admin);

        var result = await _sut.ChangeUserRoleAsync(admin.Id, admin.Id, new ChangeUserRoleRequest("User"));

        Assert.True(result.IsFailure);
        Assert.Equal(ErrorType.Validation, result.ErrorType);
        Assert.Equal(0, _uow.SaveCount);
    }

    [Fact]
    public async Task ChangeUserStatusAsync_DeactivatingLastAdmin_ReturnsValidationError()
    {
        var actorId = Guid.NewGuid();
        var onlyAdmin = User.Create("only@example.com", "Only Admin", "hash", Role.AdminRoleId);
        _userRepo.Users.Add(onlyAdmin);

        var result = await _sut.ChangeUserStatusAsync(actorId, onlyAdmin.Id, new ChangeUserStatusRequest(false));

        Assert.True(result.IsFailure);
        Assert.Equal(ErrorType.Validation, result.ErrorType);
    }

    private sealed class FakeUserRepo : IUserRepository
    {
        public List<User> Users { get; } = [];
        public Task<User?> GetByIdWithRoleAsync(Guid id, CancellationToken cancellationToken = default)
            => Task.FromResult(Users.FirstOrDefault(u => u.Id == id));
        public Task<User?> GetByEmailWithRoleAsync(string normalizedEmail, CancellationToken cancellationToken = default)
            => Task.FromResult(Users.FirstOrDefault(u => u.Email == normalizedEmail));
        public Task<bool> ExistsByEmailAsync(string normalizedEmail, CancellationToken cancellationToken = default)
            => Task.FromResult(Users.Any(u => u.Email == normalizedEmail));
        public Task<IReadOnlyList<User>> ListWithRolesAsync(string? search = null, int limit = 50, int offset = 0, CancellationToken cancellationToken = default)
            => Task.FromResult<IReadOnlyList<User>>(Users);
        public Task<IReadOnlyList<User>> ListActiveAdminsAsync(CancellationToken cancellationToken = default)
            => Task.FromResult<IReadOnlyList<User>>(Users.Where(u => u.IsActive && u.RoleId == Role.AdminRoleId).ToList());
        public Task<int> CountActiveAdminsAsync(CancellationToken cancellationToken = default)
            => Task.FromResult(Users.Count(u => u.IsActive && u.RoleId == Role.AdminRoleId));
        public Task AddAsync(User user, CancellationToken cancellationToken = default)
        {
            Users.Add(user);
            return Task.CompletedTask;
        }
    }

    private sealed class FakeRoleRepo : IRoleRepository
    {
        private readonly List<Role> _roles =
        [
            Role.Create("User", "Standard user", Role.UserRoleId),
            Role.Create("Admin", "Administrator", Role.AdminRoleId),
        ];

        public Task<Role?> GetByIdAsync(Guid id, CancellationToken cancellationToken = default)
            => Task.FromResult(_roles.FirstOrDefault(r => r.Id == id));
        public Task<Role?> GetByNameAsync(string name, CancellationToken cancellationToken = default)
            => Task.FromResult(_roles.FirstOrDefault(r => r.Name.Equals(name, StringComparison.OrdinalIgnoreCase)));
        public Task<IReadOnlyList<Role>> ListAllAsync(CancellationToken cancellationToken = default)
            => Task.FromResult<IReadOnlyList<Role>>(_roles);
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

    private sealed class FakeClock(DateTime utcNow) : IDateTimeProvider
    {
        public DateTime UtcNow { get; } = utcNow;
    }

    private sealed class FakeCache : ICacheProvider
    {
        public List<string> ClearedPrefixes { get; } = [];
        public Task<byte[]?> GetAsync(string key, CancellationToken cancellationToken = default) => Task.FromResult<byte[]?>(null);
        public Task SetAsync(string key, byte[] value, int? ttlSeconds = null, CancellationToken cancellationToken = default) => Task.CompletedTask;
        public Task DeleteAsync(string key, CancellationToken cancellationToken = default) => Task.CompletedTask;
        public Task<int> ClearPrefixAsync(string prefix, CancellationToken cancellationToken = default)
        {
            ClearedPrefixes.Add(prefix);
            return Task.FromResult(1);
        }
        public Task<bool> HealthCheckAsync(CancellationToken cancellationToken = default) => Task.FromResult(true);
    }
}
