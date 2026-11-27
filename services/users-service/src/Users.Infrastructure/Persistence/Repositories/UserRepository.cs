using Microsoft.EntityFrameworkCore;
using Users.Application.Common.Interfaces.Repositories;
using Users.Domain.Entities;

namespace Users.Infrastructure.Persistence.Repositories;

public sealed class UserRepository(UsersDbContext dbContext) : IUserRepository
{
    public async Task<User?> GetByIdWithRoleAsync(Guid id, CancellationToken cancellationToken = default)
    {
        return await dbContext.Users
            .Include(u => u.Role)
            .FirstOrDefaultAsync(u => u.Id == id, cancellationToken);
    }

    public async Task<User?> GetByEmailWithRoleAsync(string normalizedEmail, CancellationToken cancellationToken = default)
    {
        return await dbContext.Users
            .Include(u => u.Role)
            .FirstOrDefaultAsync(u => u.Email == normalizedEmail, cancellationToken);
    }

    public async Task<bool> ExistsByEmailAsync(string normalizedEmail, CancellationToken cancellationToken = default)
    {
        return await dbContext.Users
            .AnyAsync(u => u.Email == normalizedEmail, cancellationToken);
    }

    public async Task<IReadOnlyList<User>> ListWithRolesAsync(
        string? search = null,
        int limit = 50,
        int offset = 0,
        CancellationToken cancellationToken = default)
    {
        var clampedLimit = Math.Clamp(limit, 1, 100);
        var clampedOffset = Math.Max(0, offset);

        var query = dbContext.Users
            .AsNoTracking()
            .Include(u => u.Role)
            .AsQueryable();

        if (!string.IsNullOrWhiteSpace(search))
        {
            var term = search.Trim().ToLowerInvariant();
            query = query.Where(u =>
                u.Email.ToLower().Contains(term)
                || u.FullName.ToLower().Contains(term));
        }

        return await query
            .OrderByDescending(u => u.CreatedAtUtc)
            .Skip(clampedOffset)
            .Take(clampedLimit)
            .ToListAsync(cancellationToken);
    }

    public async Task<IReadOnlyList<User>> ListActiveAdminsAsync(CancellationToken cancellationToken = default)
    {
        return await dbContext.Users
            .AsNoTracking()
            .Where(u => u.IsActive && u.RoleId == Role.AdminRoleId)
            .ToListAsync(cancellationToken);
    }

    public async Task<int> CountActiveAdminsAsync(CancellationToken cancellationToken = default)
    {
        return await dbContext.Users
            .CountAsync(u => u.IsActive && u.RoleId == Role.AdminRoleId, cancellationToken);
    }

    public async Task AddAsync(User user, CancellationToken cancellationToken = default)
    {
        await dbContext.Users.AddAsync(user, cancellationToken);
    }
}
