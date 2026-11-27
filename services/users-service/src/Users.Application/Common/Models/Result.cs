namespace Users.Application.Common.Models;

public enum ErrorType
{
    None = 0,
    Validation = 1,
    Unauthorized = 2,
    Forbidden = 3,
    NotFound = 4,
    Conflict = 5,
}

public class Result
{
    public bool IsSuccess { get; }
    public bool IsFailure => !IsSuccess;
    public string? ErrorMessage { get; }
    public ErrorType ErrorType { get; }

    protected Result(bool isSuccess, string? errorMessage, ErrorType errorType)
    {
        IsSuccess = isSuccess;
        ErrorMessage = errorMessage;
        ErrorType = errorType;
    }

    public static Result Success() => new(true, null, ErrorType.None);
    public static Result Validation(string message) => new(false, message, ErrorType.Validation);
    public static Result Unauthorized(string message) => new(false, message, ErrorType.Unauthorized);
    public static Result Forbidden(string message) => new(false, message, ErrorType.Forbidden);
    public static Result NotFound(string message) => new(false, message, ErrorType.NotFound);
    public static Result Conflict(string message) => new(false, message, ErrorType.Conflict);
}

public sealed class Result<T> : Result
{
    public T? Value { get; }

    private Result(bool isSuccess, T? value, string? errorMessage, ErrorType errorType)
        : base(isSuccess, errorMessage, errorType)
    {
        Value = value;
    }

    public static Result<T> Success(T value) => new(true, value, null, ErrorType.None);
    public new static Result<T> Validation(string message) => new(false, default, message, ErrorType.Validation);
    public new static Result<T> Unauthorized(string message) => new(false, default, message, ErrorType.Unauthorized);
    public new static Result<T> Forbidden(string message) => new(false, default, message, ErrorType.Forbidden);
    public new static Result<T> NotFound(string message) => new(false, default, message, ErrorType.NotFound);
    public new static Result<T> Conflict(string message) => new(false, default, message, ErrorType.Conflict);
}
