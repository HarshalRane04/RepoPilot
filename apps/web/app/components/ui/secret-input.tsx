export function SecretInput({
  action,
  label,
  name,
  onChange,
  placeholder,
  secret,
  value
}: {
  action?: React.ReactNode;
  label: string;
  name: string;
  onChange: (value: string) => void;
  placeholder: string;
  secret?: boolean;
  value: string;
}) {
  return (
    <label className="secretInput">
      <span>{label}</span>
      <div>
        <input
          autoCapitalize="none"
          autoComplete="off"
          autoCorrect="off"
          name={name}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          spellCheck={false}
          type={secret ? "password" : "text"}
          value={value}
        />
        {action}
      </div>
    </label>
  );
}
