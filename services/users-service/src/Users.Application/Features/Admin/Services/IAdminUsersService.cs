using Users.Application.Common.Models;
using Users.Application.Features.Admin.DTOs;

namespace Users.Application.Features.Admin.Services;

public interface IAdminUsersService
{
    Task<Result<IReadOnlyList<RoleResponse>>> ListRolesAsync(CancellationToken cancellationToken = default);

    Task<Result<IReadOnlyList<AdminUserResponse>>> ListUsersAsync(
        string? search = null,
        int limit = 50,
        int offset = 0,
        CancellationToken cancellationToken = default);

    Task<Result<AdminUserResponse>> ChangeUserRoleAsync(
        Guid actorUserId,
        Guid targetUserId,
        ChangeUserRoleRequest request,
        CancellationToken cancellationToken = default);

    Task<Result<AdminUserResponse>> ChangeUserStatusAsync(
        Guid actorUserId,
        Guid targetUserId,
        ChangeUserStatusRequest request,
        CancellationToken cancellationToken = default);
}
