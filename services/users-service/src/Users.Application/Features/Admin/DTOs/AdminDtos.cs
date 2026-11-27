namespace Users.Application.Features.Admin.DTOs;

public sealed record RoleResponse(
    Guid Id,
    string Name,
    string? Description);

public sealed record AdminUserResponse(
    Guid Id,
    string Email,
    string FullName,
    string Role,
    Guid RoleId,
    bool IsActive,
    bool EmailVerified,
    DateTime CreatedAtUtc);

public sealed record ChangeUserRoleRequest(string Role);

public sealed record ChangeUserStatusRequest(bool IsActive);
