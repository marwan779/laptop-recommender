namespace Users.Application.Features.Auth.DTOs;

public sealed record LoginRequest(
    string Email,
    string Password);
