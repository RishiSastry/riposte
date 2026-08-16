//! `riposte-c` — the Riposte compiler CLI.
//!
//! Pipeline (SPEC §5): lex → parse (with recovery) → name/scope+structure check → emit.
//! `riposte-c build bot.rpo` always writes `bot.diag.json`; on success it also writes
//! `bot.policy.json` (the IR the Python runtime interprets).

use std::path::{Path, PathBuf};
use std::process::ExitCode;

use clap::{Parser, Subcommand};
use riposte_c::compile;

#[derive(Parser)]
#[command(name = "riposte-c", version, about = "Riposte compiler")]
struct Cli {
    #[command(subcommand)]
    cmd: Cmd,
}

#[derive(Subcommand)]
enum Cmd {
    /// Compile a .rpo program to policy.json (+ always diag.json).
    Build {
        /// Path to the .rpo source file.
        file: PathBuf,
        /// Directory for outputs (default: alongside the source).
        #[arg(long)]
        out_dir: Option<PathBuf>,
        /// Also print the policy JSON to stdout on success.
        #[arg(long)]
        stdout: bool,
    },
}

fn main() -> ExitCode {
    let cli = Cli::parse();
    match cli.cmd {
        Cmd::Build { file, out_dir, stdout } => build(&file, out_dir.as_deref(), stdout),
    }
}

fn build(file: &Path, out_dir: Option<&Path>, to_stdout: bool) -> ExitCode {
    let src = match std::fs::read_to_string(file) {
        Ok(s) => s,
        Err(e) => {
            eprintln!("riposte-c: cannot read {}: {e}", file.display());
            return ExitCode::FAILURE;
        }
    };
    let name = file.file_name().and_then(|s| s.to_str()).unwrap_or("input.rpo").to_string();

    let compiled = compile(&name, &src);

    // output paths
    let stem = file.file_stem().and_then(|s| s.to_str()).unwrap_or("out");
    let dir = out_dir
        .map(Path::to_path_buf)
        .unwrap_or_else(|| file.parent().map(Path::to_path_buf).unwrap_or_default());
    let diag_path = dir.join(format!("{stem}.diag.json"));
    let policy_path = dir.join(format!("{stem}.policy.json"));

    if let Err(e) = std::fs::write(&diag_path, pretty(&compiled.report)) {
        eprintln!("riposte-c: cannot write {}: {e}", diag_path.display());
        return ExitCode::FAILURE;
    }

    let n_err = count(&compiled.report, "error");
    let n_warn = count(&compiled.report, "warning");

    match compiled.policy {
        Some(policy) => {
            let policy_str = pretty(&policy);
            if let Err(e) = std::fs::write(&policy_path, &policy_str) {
                eprintln!("riposte-c: cannot write {}: {e}", policy_path.display());
                return ExitCode::FAILURE;
            }
            if to_stdout {
                println!("{policy_str}");
            }
            eprintln!(
                "✓ compiled → {} ({n_warn} warning(s), diag: {})",
                policy_path.display(),
                diag_path.display()
            );
            ExitCode::SUCCESS
        }
        None => {
            eprintln!("✗ {n_err} error(s), {n_warn} warning(s) → {}", diag_path.display());
            ExitCode::FAILURE
        }
    }
}

fn count(report: &serde_json::Value, severity: &str) -> usize {
    report["diagnostics"]
        .as_array()
        .map(|ds| ds.iter().filter(|d| d["severity"] == severity).count())
        .unwrap_or(0)
}

fn pretty(v: &serde_json::Value) -> String {
    let mut s = serde_json::to_string_pretty(v).expect("json");
    s.push('\n');
    s
}
