export default function Button({ onClick, children, variant = 'primary', disabled = false, ...props }) {
  const className = `btn btn--${variant}`

  return (
    <button
      className={className}
      onClick={onClick}
      disabled={disabled}
      {...props}
    >
      {children}
    </button>
  )
}