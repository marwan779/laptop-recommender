using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Users.Application.Features.Admin.DTOs;
using Users.Application.Features.Admin.Services;
using Users.Application.Features.Feedback.DTOs;
using Users.Application.Features.Feedback.Services;

namespace Users.Api.Areas.Users.Controllers;

[Authorize(Roles = "Admin")]
public sealed class AdminController(
    IAdminUsersService adminUsersService,
    IFeedbackService feedbackService) : UsersBaseController
{
    [HttpGet("roles")]
    [ProducesResponseType(typeof(IReadOnlyList<RoleResponse>), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType(StatusCodes.Status403Forbidden)]
    public async Task<IActionResult> ListRoles(CancellationToken cancellationToken)
    {
        var result = await adminUsersService.ListRolesAsync(cancellationToken);
        return ToActionResult(result);
    }

    [HttpGet("users")]
    [ProducesResponseType(typeof(IReadOnlyList<AdminUserResponse>), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType(StatusCodes.Status403Forbidden)]
    public async Task<IActionResult> ListUsers(
        [FromQuery] string? search = null,
        [FromQuery] int limit = 50,
        [FromQuery] int offset = 0,
        CancellationToken cancellationToken = default)
    {
        var result = await adminUsersService.ListUsersAsync(search, limit, offset, cancellationToken);
        return ToActionResult(result);
    }

    [HttpPatch("users/{userId:guid}/role")]
    [ProducesResponseType(typeof(AdminUserResponse), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType(StatusCodes.Status403Forbidden)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> ChangeUserRole(
        Guid userId,
        [FromBody] ChangeUserRoleRequest request,
        CancellationToken cancellationToken)
    {
        var actorId = GetCurrentUserId();
        if (actorId is null)
        {
            return Unauthorized();
        }

        var result = await adminUsersService.ChangeUserRoleAsync(actorId.Value, userId, request, cancellationToken);
        return ToActionResult(result);
    }

    [HttpPatch("users/{userId:guid}/status")]
    [ProducesResponseType(typeof(AdminUserResponse), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType(StatusCodes.Status403Forbidden)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> ChangeUserStatus(
        Guid userId,
        [FromBody] ChangeUserStatusRequest request,
        CancellationToken cancellationToken)
    {
        var actorId = GetCurrentUserId();
        if (actorId is null)
        {
            return Unauthorized();
        }

        var result = await adminUsersService.ChangeUserStatusAsync(actorId.Value, userId, request, cancellationToken);
        return ToActionResult(result);
    }

    [HttpGet("feedback")]
    [ProducesResponseType(typeof(IReadOnlyList<FeedbackResponse>), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType(StatusCodes.Status403Forbidden)]
    public async Task<IActionResult> ListFeedback(
        [FromQuery] string? status = null,
        [FromQuery] string? category = null,
        [FromQuery] int limit = 50,
        [FromQuery] int offset = 0,
        CancellationToken cancellationToken = default)
    {
        var result = await feedbackService.ListAllForAdminAsync(status, category, limit, offset, cancellationToken);
        return ToActionResult(result);
    }

    [HttpPatch("feedback/{feedbackId:guid}")]
    [ProducesResponseType(typeof(FeedbackResponse), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType(StatusCodes.Status403Forbidden)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> ReviewFeedback(
        Guid feedbackId,
        [FromBody] UpdateFeedbackStatusRequest request,
        CancellationToken cancellationToken)
    {
        var actorId = GetCurrentUserId();
        if (actorId is null)
        {
            return Unauthorized();
        }

        var result = await feedbackService.ReviewAsync(actorId.Value, feedbackId, request, cancellationToken);
        return ToActionResult(result);
    }
}
