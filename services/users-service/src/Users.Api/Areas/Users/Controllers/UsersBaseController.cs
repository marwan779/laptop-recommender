using Microsoft.AspNetCore.Mvc;
using Users.Application.Common.Models;

namespace Users.Api.Areas.Users.Controllers;

[ApiController]
[Area("Users")]
[Route("api/v1/users/[controller]")]
public abstract class UsersBaseController : ControllerBase
{
    protected IActionResult ToActionResult(Result result)
    {
        if (result.IsSuccess)
        {
            return Ok();
        }

        return ToErrorResult(result);
    }

    protected IActionResult ToActionResult<T>(Result<T> result)
    {
        if (result.IsSuccess)
        {
            return Ok(result.Value);
        }

        return ToErrorResult(result);
    }

    private IActionResult ToErrorResult(Result result)
    {
        var statusCode = result.ErrorType switch
        {
            ErrorType.Validation => StatusCodes.Status400BadRequest,
            ErrorType.Unauthorized => StatusCodes.Status401Unauthorized,
            ErrorType.Forbidden => StatusCodes.Status403Forbidden,
            ErrorType.NotFound => StatusCodes.Status404NotFound,
            ErrorType.Conflict => StatusCodes.Status409Conflict,
            _ => StatusCodes.Status400BadRequest,
        };

        return Problem(
            detail: result.ErrorMessage,
            statusCode: statusCode);
    }
}
