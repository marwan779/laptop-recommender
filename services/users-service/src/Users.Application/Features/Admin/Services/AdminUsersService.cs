using Users.Application.Common.Interfaces;
using Users.Application.Common.Interfaces.Caching;
using Users.Application.Common.Interfaces.Repositories;
using Users.Application.Common.Models;
using Users.Application.Features.Admin.DTOs;
using Users.Domain.Entities;

namespace Users.Application.Features.Admin.Services;

public sealed class AdminUsersService(
    IUserRepository userRepository,
    IRoleRepository roleRepository,
    IUnitOfWork unitOfWork,
    IDateTimeProvider dateTimeProvider,
    ICacheProvider cacheProvider) : IAdminUsersService
{
    public async Task<Result<IReadOnlyList<RoleResponse>>> ListRolesAsync(
        CancellationToken cancellationToken = default)
    {
        var roles = await roleRepository.ListAllAsync(cancellationToken);
        return Result<IReadOnlyList<RoleResponse>>.Success(
            roles.Select(r => new RoleResponse(r.Id, r.Name, r.Description)).ToList());
    }

    public async Task<Result<IReadOnlyList<AdminUserResponse>>> ListUsersAsync(
        string? search = null,
        int limit = 50,
        int offset = 0,
        CancellationToken cancellationToken = default)
    {
        var users = await userRepository.ListWithRolesAsync(search, limit, offset, cancellationToken);
        return Result<IReadOnlyList<AdminUserResponse>>.Success(
            users.Select(u => MapToResponse(u, u.Role?.Name ?? ResolveFallbackRoleName(u.RoleId))).ToList());
    }

    public async Task<Result<AdminUserResponse>> ChangeUserRoleAsync(
        Guid actorUserId,
        Guid targetUserId,
        ChangeUserRoleRequest request,
        CancellationToken cancellationToken = default)
    {
        var roleName = (request.Role ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(roleName))
        {
            return Result<AdminUserResponse>.Validation("Role name is required.");
        }

        var targetRole = await roleRepository.GetByNameAsync(roleName, cancellationToken);
        if (targetRole is null)
        {
            return Result<AdminUserResponse>.Validation($"Role '{roleName}' does not exist.");
        }

        var user = await userRepository.GetByIdWithRoleAsync(targetUserId, cancellationToken);
        if (user is null)
        {
            return Result<AdminUserResponse>.NotFound("User was not found.");
        }

        if (actorUserId == targetUserId && targetRole.Id != Role.AdminRoleId)
        {
            return Result<AdminUserResponse>.Validation("You cannot remove your own Admin role.");
        }

        if (user.RoleId == Role.AdminRoleId && targetRole.Id != Role.AdminRoleId)
        {
            var activeAdmins = await userRepository.CountActiveAdminsAsync(cancellationToken);
            if (activeAdmins <= 1)
            {
                return Result<AdminUserResponse>.Validation("At least one active Admin account must remain.");
            }
        }

        user.ChangeRole(targetRole.Id, dateTimeProvider.UtcNow);
        await unitOfWork.SaveChangesAsync(cancellationToken);
        await cacheProvider.ClearPrefixAsync($"users:{targetUserId}:profile:", cancellationToken);

        return Result<AdminUserResponse>.Success(MapToResponse(user, targetRole.Name));
    }

    public async Task<Result<AdminUserResponse>> ChangeUserStatusAsync(
        Guid actorUserId,
        Guid targetUserId,
        ChangeUserStatusRequest request,
        CancellationToken cancellationToken = default)
    {
        var user = await userRepository.GetByIdWithRoleAsync(targetUserId, cancellationToken);
        if (user is null)
        {
            return Result<AdminUserResponse>.NotFound("User was not found.");
        }

        if (actorUserId == targetUserId && !request.IsActive)
        {
            return Result<AdminUserResponse>.Validation("You cannot deactivate your own Admin account.");
        }

        if (user.RoleId == Role.AdminRoleId && user.IsActive && !request.IsActive)
        {
            var activeAdmins = await userRepository.CountActiveAdminsAsync(cancellationToken);
            if (activeAdmins <= 1)
            {
                return Result<AdminUserResponse>.Validation("At least one active Admin account must remain.");
            }
        }

        if (request.IsActive)
        {
            user.Activate(dateTimeProvider.UtcNow);
        }
        else
        {
            user.Deactivate(dateTimeProvider.UtcNow);
        }

        await unitOfWork.SaveChangesAsync(cancellationToken);
        await cacheProvider.ClearPrefixAsync($"users:{targetUserId}:profile:", cancellationToken);

        return Result<AdminUserResponse>.Success(
            MapToResponse(user, user.Role?.Name ?? ResolveFallbackRoleName(user.RoleId)));
    }

    private static string ResolveFallbackRoleName(Guid roleId)
        => roleId == Role.AdminRoleId ? "Admin" : "User";

    private static AdminUserResponse MapToResponse(User user, string roleName)
        => new(
            user.Id,
            user.Email,
            user.FullName,
            roleName,
            user.RoleId,
            user.IsActive,
            user.EmailVerified,
            user.CreatedAtUtc);
}
