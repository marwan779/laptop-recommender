using System.Security.Claims;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Users.Application.Features.Feedback.DTOs;
using Users.Application.Features.Feedback.Services;

namespace Users.Api.Areas.Users.Controllers;

public sealed class FeedbackController(IFeedbackService feedbackService) : UsersBaseController
{
    [HttpPost]
    [AllowAnonymous]
    [ProducesResponseType(typeof(FeedbackResponse), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public async Task<IActionResult> Submit(
        [FromBody] CreateFeedbackRequest request,
        CancellationToken cancellationToken)
    {
        var userId = GetCurrentUserId();
        var email = User.FindFirstValue(ClaimTypes.Email) ?? User.FindFirstValue("email");
        var result = await feedbackService.SubmitAsync(userId, email, request, cancellationToken);
        return ToActionResult(result);
    }

    [HttpGet("mine")]
    [Authorize]
    [ProducesResponseType(typeof(IReadOnlyList<FeedbackResponse>), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    public async Task<IActionResult> GetMyReports(
        [FromQuery] int limit = 50,
        CancellationToken cancellationToken = default)
    {
        var userId = GetCurrentUserId();
        if (userId is null)
        {
            return Unauthorized();
        }

        var result = await feedbackService.GetMyReportsAsync(userId.Value, limit, cancellationToken);
        return ToActionResult(result);
    }
}
