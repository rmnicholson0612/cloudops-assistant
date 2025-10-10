// Security Hub App Module

let allFindings = [];
let complianceData = {};
let currentTab = 'findings';

// Make variables globally accessible
window.allFindings = allFindings;
window.complianceData = complianceData;
window.currentTab = currentTab;

function initializeSecurityHub() {
    loadSecurityData();
    loadComplianceData();
}

async function loadSecurityData() {
    await loadSecuritySummary();
    await loadResourcesView();
}

async function loadSecuritySummary() {
    if (!API.isAuthenticated()) {
        document.getElementById('security-score').textContent = '--';
        document.getElementById('last-scan-time').textContent = 'Please login first';
        resetVulnerabilityButtons();
        return;
    }

    try {
        const findings = await API.get('/security/findings');
        updateSecuritySummary(findings);
    } catch (error) {
        document.getElementById('security-score').textContent = '--';
        document.getElementById('last-scan-time').textContent = 'No scans available';
        resetVulnerabilityButtons();
    }
}

function updateSecuritySummary(findings) {
    const counts = { critical: 0, high: 0, medium: 0, low: 0, passed: 0 };

    findings.forEach(finding => {
        const severity = finding.severity.toLowerCase();
        const status = finding.status;

        if (status === 'PASS' || severity === 'pass') {
            counts.passed++;
        } else if (counts.hasOwnProperty(severity)) {
            counts[severity]++;
        } else {
            if (status === 'FAIL') {
                counts.medium++;
            } else {
                counts.passed++;
            }
        }
    });

    // Update vulnerability buttons
    document.getElementById('critical-count').textContent = counts.critical;
    document.getElementById('high-count').textContent = counts.high;
    document.getElementById('medium-count').textContent = counts.medium;
    document.getElementById('low-count').textContent = counts.low;
    document.getElementById('passed-count').textContent = counts.passed;

    // Calculate security score
    const total = Object.values(counts).reduce((a, b) => a + b, 0);
    const score = total > 0 ? Math.round((counts.passed / total) * 100) : 100;

    document.getElementById('security-score').textContent = score + '%';
    document.getElementById('last-scan-time').textContent = 'Last scan: ' + new Date().toLocaleString();

    updateSecurityGauge(score);
}

function resetVulnerabilityButtons() {
    ['critical', 'high', 'medium', 'low', 'passed'].forEach(severity => {
        document.getElementById(severity + '-count').textContent = '--';
    });
}

function updateSecurityGauge(score) {
    const angle = (score / 100) * 160;
    const radians = (angle - 80) * (Math.PI / 180);
    const x = 100 + 80 * Math.cos(radians);
    const y = 100 + 80 * Math.sin(radians);

    const needle = document.getElementById('gauge-needle');
    needle.setAttribute('x2', x);
    needle.setAttribute('y2', y);

    const largeArcFlag = angle > 80 ? 1 : 0;
    const endX = 100 + 80 * Math.cos((angle - 80) * Math.PI / 180);
    const endY = 100 + 80 * Math.sin((angle - 80) * Math.PI / 180);
    const pathData = `M 20 100 A 80 80 0 ${largeArcFlag} 1 ${endX} ${endY}`;

    document.getElementById('gauge-fill').setAttribute('d', pathData);
}

async function runSecurityScan() {
    if (!API.requireAuth()) return;

    const button = event.target.closest('button');
    const originalText = button.innerHTML;
    button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Scanning...';
    button.disabled = true;

    try {
        await API.post('/security/scan', {
            services: ['iam', 's3', 'ec2', 'cloudtrail', 'config', 'cloudwatch', 'kms', 'rds', 'lambda'],
            regions: ['us-east-1']
        });

        await loadSecurityData();
        alert('Security scan completed successfully!');
    } catch (error) {
        alert(`Scan failed: ${error.message}`);
    } finally {
        button.innerHTML = originalText;
        button.disabled = false;
    }
}

async function showVulnerabilities(severity) {
    if (!API.requireAuth()) return;

    try {
        const findings = await API.get('/security/findings');
        const filteredFindings = findings.filter(f => f.severity.toLowerCase() === severity.toLowerCase());

        if (filteredFindings.length === 0) {
            alert(`No ${severity} severity findings found`);
            return;
        }

        displaySecurityFindings(filteredFindings);
    } catch (error) {
        alert(`Error loading findings: ${error.message}`);
    }
}

async function loadResourcesView() {
    const display = document.getElementById('resources-display');
    if (!display) return;

    const filter = document.getElementById('resource-status-filter');
    if (filter) filter.value = 'all';

    if (!API.isAuthenticated()) {
        display.innerHTML = '<p>Please login to view security findings</p>';
        return;
    }

    try {
        const findings = await API.get('/security/findings');
        displaySecurityFindings(findings);
    } catch (error) {
        display.innerHTML = '<p>No security findings available. Run a scan first.</p>';
    }
}

function displaySecurityFindings(findings) {
    allFindings = findings;
    const display = document.getElementById('resources-display');

    if (!findings || findings.length === 0) {
        display.innerHTML = '<p>No security findings. Your infrastructure looks secure! 🎉</p>';
        return;
    }

    display.innerHTML = findings.map(finding => {
        const cveLink = getCVELink(finding.check_id, finding.severity);
        return `
            <div class="resource-item ${finding.severity.toLowerCase()}" data-status="${finding.severity.toLowerCase()}">
                <div class="resource-header">
                    <h4>${finding.resource_id || 'Unknown Resource'}</h4>
                    <span class="resource-type">${finding.service}</span>
                    <span class="account-badge">${finding.region}</span>
                </div>
                <p>${finding.description}</p>
                <div class="findings-summary">
                    <span class="finding ${finding.severity.toLowerCase()}">${finding.severity}</span>
                    ${cveLink}
                    ${finding.compliance ? `<div class="compliance-tags">${finding.compliance.map(c => `<span class="compliance-tag">${c}</span>`).join('')}</div>` : ''}
                </div>
            </div>
        `;
    }).join('');
}

function filterResourcesByStatus() {
    const filter = document.getElementById('resource-status-filter').value;
    const display = document.getElementById('resources-display');

    if (!allFindings || allFindings.length === 0) {
        return;
    }

    let filteredFindings = allFindings;
    if (filter !== 'all') {
        filteredFindings = allFindings.filter(finding => {
            const severity = finding.severity.toLowerCase();
            const status = finding.status;

            if (filter === 'passed') {
                return status === 'PASS' || severity === 'pass';
            }
            return severity === filter;
        });
    }

    if (filteredFindings.length === 0) {
        display.innerHTML = `<p>No ${filter === 'all' ? '' : filter} findings found.</p>`;
        return;
    }

    displaySecurityFindings(filteredFindings);
}

// Tab Management (enhanced version)
function switchTab(tabName) {
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    document.querySelector(`[onclick="switchTab('${tabName}')"]`).classList.add('active');

    document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
    document.getElementById(`${tabName}-tab`).classList.add('active');

    window.currentTab = currentTab = tabName;

    if (tabName === 'compliance' && Object.keys(complianceData).length === 0) {
        loadComplianceData();
    }
}

// Compliance Data Management
async function loadComplianceData() {
    if (!API.isAuthenticated()) {
        document.getElementById('compliance-display').innerHTML = '<p>Please login to view compliance data</p>';
        return;
    }

    try {
        const [compliance, rules] = await Promise.all([
            API.get('/security/compliance'),
            API.get('/security/compliance/rules')
        ]);
        complianceData = { summary: compliance, rules: rules };
        displayComplianceData(compliance, rules);
    } catch (error) {
        document.getElementById('compliance-display').innerHTML = '<p>No compliance data available. Run a scan first.</p>';
    }
}

function displayComplianceData(compliance, rules) {
    const display = document.getElementById('compliance-display');

    if (!compliance || Object.keys(compliance).length === 0) {
        display.innerHTML = '<p>No compliance data available. Run a security scan first.</p>';
        return;
    }

    const frameworks = Object.keys(compliance).sort();

    display.innerHTML = frameworks.map(framework => {
        const data = compliance[framework];
        const passRate = data.total > 0 ? Math.round(((data.total - data.critical - data.high - data.medium - data.low) / data.total) * 100) : 100;
        const frameworkRules = rules[framework] || { rules: [] };

        return `
            <div class="compliance-framework" data-framework="${framework}">
                <div class="framework-header">
                    <h4>${getFrameworkName(framework)}</h4>
                    <div class="framework-score ${getScoreClass(passRate)}">
                        ${passRate}% Compliant
                    </div>
                </div>
                <div class="framework-stats">
                    <div class="stat-item critical">
                        <span class="stat-count">${data.critical}</span>
                        <span class="stat-label">Critical</span>
                    </div>
                    <div class="stat-item high">
                        <span class="stat-count">${data.high}</span>
                        <span class="stat-label">High</span>
                    </div>
                    <div class="stat-item medium">
                        <span class="stat-count">${data.medium}</span>
                        <span class="stat-label">Medium</span>
                    </div>
                    <div class="stat-item low">
                        <span class="stat-count">${data.low}</span>
                        <span class="stat-label">Low</span>
                    </div>
                    <div class="stat-item not-applicable">
                        <span class="stat-count">${data.not_applicable}</span>
                        <span class="stat-label">N/A</span>
                    </div>
                </div>
                <div class="framework-progress">
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: ${passRate}%"></div>
                    </div>
                    <span class="progress-text">${data.total - data.critical - data.high - data.medium - data.low} of ${data.total} checks passed</span>
                </div>
                <div class="framework-rules">
                    <button class="btn btn-secondary" onclick="toggleRules('${framework}')">
                        <i class="fas fa-list"></i> View Rules (${frameworkRules.rules.length})
                    </button>
                    <div id="rules-${framework}" class="rules-list" style="display: none;">
                        ${frameworkRules.rules.map(rule => `
                            <div class="rule-item">
                                <div class="rule-header">
                                    <h5>${rule.title}</h5>
                                    <span class="rule-severity ${rule.severity.toLowerCase()}">${rule.severity}</span>
                                </div>
                                <p class="rule-description">${rule.description}</p>
                                <div class="rule-details">
                                    <span class="rule-id">${rule.framework_rule}</span>
                                    ${rule.cve_references.length > 0 ? `
                                        <div class="cve-references">
                                            ${rule.cve_references.map(cve => `
                                                <a href="https://cve.mitre.org/cgi-bin/cvename.cgi?name=${cve}" target="_blank" class="cve-link">
                                                    <i class="fas fa-external-link-alt"></i> ${cve}
                                                </a>
                                            `).join('')}
                                        </div>
                                    ` : ''}
                                </div>
                                <div class="rule-remediation">
                                    <strong>Remediation:</strong> ${rule.remediation}
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

function getFrameworkName(framework) {
    const names = {
        'CIS': 'CIS Controls',
        'NIST': 'NIST Cybersecurity Framework',
        'PCI': 'PCI-DSS',
        'SOC2': 'SOC 2 Type II'
    };
    return names[framework] || framework;
}

function getScoreClass(score) {
    if (score >= 90) return 'excellent';
    if (score >= 75) return 'good';
    if (score >= 50) return 'fair';
    return 'poor';
}

function filterComplianceFramework() {
    const filter = document.getElementById('compliance-framework-filter').value;
    const frameworks = document.querySelectorAll('.compliance-framework');

    frameworks.forEach(framework => {
        const frameworkName = framework.dataset.framework;
        if (filter === 'all' || frameworkName === filter) {
            framework.style.display = 'block';
        } else {
            framework.style.display = 'none';
        }
    });
}

function toggleRules(framework) {
    const rulesDiv = document.getElementById(`rules-${framework}`);
    const button = rulesDiv.previousElementSibling;

    if (rulesDiv.style.display === 'none') {
        rulesDiv.style.display = 'block';
        button.innerHTML = '<i class="fas fa-chevron-up"></i> Hide Rules';
    } else {
        rulesDiv.style.display = 'none';
        const rulesCount = rulesDiv.querySelectorAll('.rule-item').length;
        button.innerHTML = `<i class="fas fa-list"></i> View Rules (${rulesCount})`;
    }
}

// CVE Integration
function getCVELink(checkId, severity) {
    // Map common security checks to CVE patterns
    const cveMapping = {
        's3_bucket_public_read': 'CVE-2017-3156',
        'ec2_security_group_ssh_world_accessible': 'CVE-2019-5736',
        'iam_root_mfa_enabled': 'CVE-2020-1472',
        'rds_instance_storage_encrypted': 'CVE-2019-11043',
        's3_bucket_server_side_encryption': 'CVE-2018-1002105'
    };

    const cveId = cveMapping[checkId];
    if (cveId) {
        return `<a href="https://cve.mitre.org/cgi-bin/cvename.cgi?name=${cveId}" target="_blank" class="cve-link">
                    <i class="fas fa-external-link-alt"></i> ${cveId}
                </a>`;
    }
    return '';
}

// PDF Export Functionality
async function exportToPDF() {
    if (!window.jsPDF) {
        alert('PDF library not loaded. Please refresh the page and try again.');
        return;
    }

    const { jsPDF } = window.jsPDF;
    const doc = new jsPDF();

    // Header
    doc.setFontSize(20);
    doc.text('CloudOps Security Report', 20, 20);

    doc.setFontSize(12);
    doc.text(`Generated: ${new Date().toLocaleString()}`, 20, 30);

    let yPosition = 50;

    if (currentTab === 'findings') {
        // Export findings
        doc.setFontSize(16);
        doc.text('Security Findings', 20, yPosition);
        yPosition += 15;

        if (allFindings.length === 0) {
            doc.setFontSize(12);
            doc.text('No security findings available.', 20, yPosition);
        } else {
            allFindings.forEach((finding, index) => {
                if (yPosition > 250) {
                    doc.addPage();
                    yPosition = 20;
                }

                doc.setFontSize(12);
                doc.setFont(undefined, 'bold');
                doc.text(`${index + 1}. ${finding.resource_id || 'Unknown Resource'}`, 20, yPosition);
                yPosition += 8;

                doc.setFont(undefined, 'normal');
                doc.text(`Service: ${finding.service} | Region: ${finding.region}`, 25, yPosition);
                yPosition += 6;

                doc.text(`Severity: ${finding.severity} | Status: ${finding.status}`, 25, yPosition);
                yPosition += 6;

                const description = doc.splitTextToSize(finding.description, 160);
                doc.text(description, 25, yPosition);
                yPosition += description.length * 6 + 5;

                // Add CVE references if available
                const cveLink = getCVELink(finding.check_id, finding.severity);
                if (cveLink) {
                    doc.text('CVE Reference: ' + finding.check_id, 25, yPosition);
                    yPosition += 6;
                }

                // Add compliance tags
                if (finding.compliance && finding.compliance.length > 0) {
                    doc.text('Compliance: ' + finding.compliance.join(', '), 25, yPosition);
                    yPosition += 6;
                }

                yPosition += 5;
            });
        }
    } else if (currentTab === 'compliance') {
        // Export compliance data with rules
        doc.setFontSize(16);
        doc.text('Compliance Summary & Rules', 20, yPosition);
        yPosition += 15;

        Object.keys(complianceData.summary || {}).forEach(framework => {
            if (yPosition > 240) {
                doc.addPage();
                yPosition = 20;
            }

            const data = complianceData.summary[framework];
            const passRate = data.total > 0 ? Math.round(((data.total - data.critical - data.high - data.medium - data.low) / data.total) * 100) : 100;

            doc.setFontSize(14);
            doc.setFont(undefined, 'bold');
            doc.text(getFrameworkName(framework), 20, yPosition);
            yPosition += 10;

            doc.setFontSize(12);
            doc.setFont(undefined, 'normal');
            doc.text(`Compliance Rate: ${passRate}%`, 25, yPosition);
            yPosition += 8;

            doc.text(`Critical: ${data.critical} | High: ${data.high} | Medium: ${data.medium} | Low: ${data.low}`, 25, yPosition);
            yPosition += 8;

            doc.text(`Total Checks: ${data.total} | Not Applicable: ${data.not_applicable}`, 25, yPosition);
            yPosition += 15;

            // Add rules for this framework
            const frameworkRules = complianceData.rules[framework];
            if (frameworkRules && frameworkRules.rules.length > 0) {
                doc.setFont(undefined, 'bold');
                doc.text('Rules:', 25, yPosition);
                yPosition += 8;

                frameworkRules.rules.forEach((rule, index) => {
                    if (yPosition > 250) {
                        doc.addPage();
                        yPosition = 20;
                    }

                    doc.setFont(undefined, 'normal');
                    doc.text(`${index + 1}. ${rule.title} (${rule.severity})`, 30, yPosition);
                    yPosition += 6;

                    const ruleDesc = doc.splitTextToSize(rule.description, 150);
                    doc.text(ruleDesc, 35, yPosition);
                    yPosition += ruleDesc.length * 6 + 3;
                });

                yPosition += 10;
            }
        });
    }

    // Save the PDF
    const timestamp = new Date().toISOString().split('T')[0];
    const tabName = currentTab === 'findings' ? 'findings' : 'compliance';
    const filename = `cloudops-security-${tabName}-report-${timestamp}.pdf`;
    doc.save(filename);
}
