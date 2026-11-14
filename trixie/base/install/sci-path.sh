# Sourced by login profiles and interactive Bash. POSIX shell syntax.
for sci_command_dir in /opt/sci/bin /opt/sci/bin-rpi; do
    case ":${PATH:-}:" in
        *":$sci_command_dir:"*) ;;
        *) PATH="${PATH:+$PATH:}$sci_command_dir" ;;
    esac
done
unset sci_command_dir
export PATH
