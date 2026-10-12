use pyo3::prelude::*;
use serde::{Deserialize, Serialize};
use sysinfo::{Disks, ProcessesToUpdate, System};

#[derive(Debug, Serialize, Deserialize)]
pub struct SystemInfo {
    pub cpu_percent: f32,
    pub memory_percent: f32,
    pub memory_used_mb: u64,
    pub memory_total_mb: u64,
    pub disk_percent: f32,
    pub disk_used_gb: u64,
    pub disk_total_gb: u64,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ProcessInfo {
    pub pid: u32,
    pub name: String,
    pub cpu_percent: f32,
    pub memory_mb: u64,
}

#[pyfunction]
fn get_system_info() -> PyResult<String> {
    let mut system = System::new_all();
    system.refresh_all();
    let total_memory = system.total_memory();
    let used_memory = system.used_memory();
    let disks = Disks::new_with_refreshed_list();
    let (disk_total, disk_available) =
        disks
            .list()
            .iter()
            .fold((0u64, 0u64), |(total, available), disk| {
                (
                    total.saturating_add(disk.total_space()),
                    available.saturating_add(disk.available_space()),
                )
            });
    let disk_used = disk_total.saturating_sub(disk_available);
    let info = SystemInfo {
        cpu_percent: system.global_cpu_usage(),
        memory_percent: if total_memory == 0 {
            0.0
        } else {
            used_memory as f32 * 100.0 / total_memory as f32
        },
        memory_used_mb: used_memory / 1024 / 1024,
        memory_total_mb: total_memory / 1024 / 1024,
        disk_percent: if disk_total == 0 {
            0.0
        } else {
            disk_used as f32 * 100.0 / disk_total as f32
        },
        disk_used_gb: disk_used / 1024 / 1024 / 1024,
        disk_total_gb: disk_total / 1024 / 1024 / 1024,
    };
    Ok(serde_json::to_string(&info).unwrap())
}

#[pyfunction]
fn get_top_processes(limit: usize) -> PyResult<String> {
    let mut system = System::new();
    system.refresh_processes(ProcessesToUpdate::All, true);
    let mut processes: Vec<ProcessInfo> = system
        .processes()
        .values()
        .map(|process| ProcessInfo {
            pid: process.pid().as_u32(),
            name: process.name().to_string_lossy().into_owned(),
            cpu_percent: process.cpu_usage(),
            memory_mb: process.memory() / 1024 / 1024,
        })
        .collect();
    processes.sort_by(|a, b| b.memory_mb.cmp(&a.memory_mb));
    processes.truncate(limit.min(100));
    Ok(serde_json::to_string(&processes).unwrap())
}

#[pyfunction]
fn fast_json_parse(json: &str) -> PyResult<String> {
    let value: serde_json::Value = serde_json::from_str(json).map_err(|e| {
        PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("JSON parse error: {}", e))
    })?;
    Ok(serde_json::to_string(&value).unwrap())
}

#[pyfunction]
fn hash_string(input: &str, algorithm: &str) -> PyResult<String> {
    use std::collections::hash_map::DefaultHasher;
    use std::hash::{Hash, Hasher};

    let result = match algorithm.to_lowercase().as_str() {
        "md5" => format!("{:x}", md5::compute(input)),
        "sha1" => format!("{:x}", sha1::Sha1::digest(input.as_bytes())),
        "sha256" => format!("{:x}", sha2::Sha256::digest(input.as_bytes())),
        _ => {
            let mut hasher = DefaultHasher::new();
            input.hash(&mut hasher);
            format!("{:x}", hasher.finish())
        }
    };
    Ok(result)
}

#[pyfunction]
fn cpu_intensive_task(n: usize) -> PyResult<u64> {
    let mut sum: u64 = 0;
    for i in 0..n {
        sum = sum.wrapping_add((i as u64).wrapping_mul(1103515245).wrapping_add(12345));
    }
    Ok(sum)
}

#[pymodule]
fn onyx_rust(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(get_system_info, m)?)?;
    m.add_function(wrap_pyfunction!(get_top_processes, m)?)?;
    m.add_function(wrap_pyfunction!(fast_json_parse, m)?)?;
    m.add_function(wrap_pyfunction!(hash_string, m)?)?;
    m.add_function(wrap_pyfunction!(cpu_intensive_task, m)?)?;
    Ok(())
}
