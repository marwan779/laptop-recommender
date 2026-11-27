using Users.Domain.Entities;

namespace Users.Application.Common.Interfaces.Repositories;

public interface IUserRepository
{
    Task<User?> GetByIdWithRoleAsync(Guid id, CancellationToken cancellationToken = default);
    Task<User?> GetByEmailWithRoleAsync(string normalizedEmail, CancellationToken cancellationToken = default);
    Task<bool> ExistsByEmailAsync(string normalizedEmail, CancellationToken cancellationToken = default);
    Task<IReadOnlyList<User>> ListWithRolesAsync(string? search = null, int limit = 50, int offset = 0, CancellationToken cancellationToken = default);
    Task<int> CountActiveAdminsAsync(CancellationToken cancellationToken = default);
    Task AddAsync(User user, CancellationToken cancellationToken = default);
}
