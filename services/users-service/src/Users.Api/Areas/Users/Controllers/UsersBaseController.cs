using Microsoft.AspNetCore.Mvc;

namespace Users.Api.Areas.Users.Controllers;

[ApiController]
[Area("Users")]
[Route("api/v1/users/[controller]")]
public abstract class UsersBaseController : ControllerBase
{
}
