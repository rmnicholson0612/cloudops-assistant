// Cost Dashboard App Module

function initializeCostDashboard() {
    initializeMonthSelector();
    loadCostData();
}

// Month selector initialization
function initializeMonthSelector() {
    const selector = document.getElementById('month-selector');
    if (!selector || selector.options.length > 0) {
        return;
    }
    const currentDate = new Date();

    // Generate last 12 months
    for (let i = 0; i < 12; i++) {
        const date = new Date(currentDate.getFullYear(), currentDate.getMonth() - i, 1);
        const value = date.toISOString().slice(0, 7); // YYYY-MM format
        const text = date.toLocaleDateString('en-US', { year: 'numeric', month: 'long' });

        const option = document.createElement('option');
        option.value = value;
        option.textContent = text;
        if (i === 0) option.selected = true; // Current month selected

        selector.appendChild(option);
    }

    // Add event listener
    selector.addEventListener('change', function() {
        loadCostData();
    });
}

// Edit budget function
async function editBudget(budgetId) {
    try {
        // Get current budget data
        const response = await API.get('/budgets/status');
        const budget = response.budgets.find(b => b.budget_id === budgetId);

        if (!budget) {
            alert('Budget not found');
            return;
        }

        // Pre-fill the form with current values
        document.getElementById('budget-name').value = budget.budget_name;
        document.getElementById('budget-limit').value = budget.monthly_limit;
        document.getElementById('warn-threshold').value = budget.thresholds ? budget.thresholds[0] || 80 : 80;
        document.getElementById('alert-threshold').value = budget.thresholds ? budget.thresholds[1] || 100 : 100;
        document.getElementById('aws-service').value = budget.service_filter || 'all';
        document.getElementById('notification-email').value = budget.email || localStorage.getItem('user_email') || '';

        // Change form to edit mode
        const form = document.getElementById('budget-form');
        form.setAttribute('data-edit-mode', budgetId);

        // Update modal title and button
        document.querySelector('#budget-modal h2').textContent = 'Edit Budget Alert';
        document.querySelector('#budget-form button[type="submit"]').textContent = 'Update Budget';

        // Show modal
        showBudgetModal();

    } catch (error) {
        alert('Error loading budget data: ' + error.message);
    }
}

// Delete budget function
async function deleteBudget(budgetId) {
    if (!confirm('Are you sure you want to delete this budget alert? This action cannot be undone.')) {
        return;
    }

    try {
        await API.delete(`/budgets/delete/${encodeURIComponent(budgetId)}`);
        alert('Budget deleted successfully!');
        loadBudgetStatus();
    } catch (error) {
        alert('Error deleting budget: ' + error.message);
    }
}

// Test budget alert email function
async function testBudgetAlert() {
    if (!API.isAuthenticated()) {
        alert('Please login to test budget alerts');
        return;
    }

    const email = prompt('Enter email address to test (leave blank to use your account email):');
    if (email === null) return; // User cancelled

    try {
        const response = await API.post('/budgets/test-alert', {
            email: email || undefined,
            budget_name: 'Test Budget Alert',
            current_spending: 85.50,
            budget_limit: 100.00,
            threshold: 80
        });

        if (response) {
            alert(`Test budget alert sent successfully to ${response.email}!\n\nCheck your email (including spam folder) for the test alert.\n\nMessage ID: ${response.message_id}`);
        }
    } catch (error) {
        alert('Error sending test alert: ' + error.message);
    }
}

function getSelectedMonth() {
    const selector = document.getElementById('month-selector');
    return selector ? selector.value : null;
}

async function loadCostData() {
    const selectedMonth = getSelectedMonth();
    await Promise.all([
        loadCurrentCosts(selectedMonth),
        loadServiceCosts(selectedMonth),
        loadCostTrends(),
        loadTagCosts(selectedMonth),
        loadBudgetStatus()
    ]);
}

async function loadCurrentCosts(month = null) {
    const displayElement = document.getElementById('current-cost-display');
    if (!displayElement) return;

    if (!API.isAuthenticated()) {
        displayElement.innerHTML = '<div class="cost-error"><i class="fas fa-lock"></i> Please login to view costs</div>';
        return;
    }

    displayElement.innerHTML = '<div class="cost-loading"><i class="fas fa-spinner fa-spin"></i> Loading current costs...</div>';

    try {
        const endpoint = month ? `/costs/current?month=${month}` : '/costs/current';
        const response = await API.get(endpoint);

        displayElement.innerHTML = `
            <div class="current-cost">
                <div class="cost-amount">$${parseFloat(response.total_cost || 0).toFixed(2)}</div>
                <div class="cost-period">${response.period || 'Current Month'}</div>
                <div class="cost-updated">Last updated: ${new Date(response.last_updated || Date.now()).toLocaleString()}</div>
            </div>`;
    } catch (error) {
        displayElement.innerHTML = `<div class="cost-error">
            <i class="fas fa-exclamation-triangle"></i> Error loading costs: ${error.message}
        </div>`;
    }
}

async function loadServiceCosts(month = null) {
    const displayElement = document.getElementById('service-costs-display');
    if (!displayElement) return;

    if (!API.isAuthenticated()) {
        displayElement.innerHTML = '<div class="cost-error"><i class="fas fa-lock"></i> Please login to view service costs</div>';
        return;
    }

    displayElement.innerHTML = '<div class="cost-loading"><i class="fas fa-spinner fa-spin"></i> Loading service costs...</div>';

    try {
        const url = month ? `/costs/services?month=${month}` : '/costs/services';
        const response = await API.get(url);

        if (!response.services || response.services.length === 0) {
            displayElement.innerHTML = '<div class="no-costs">No service costs found for this period</div>';
            return;
        }

        let html = '<div class="service-list">';
        response.services.forEach(service => {
            html += `
                <div class="service-item">
                    <div class="service-name">${service.service}</div>
                    <div class="service-cost">$${parseFloat(service.cost || 0).toFixed(2)}</div>
                </div>`;
        });
        html += '</div>';

        displayElement.innerHTML = html;
    } catch (error) {
        displayElement.innerHTML = `<div class="cost-error">
            <i class="fas fa-exclamation-triangle"></i> Error loading service costs: ${error.message}
        </div>`;
    }
}

async function loadCostTrends() {
    const displayElement = document.getElementById('cost-trends-display');
    if (!displayElement) return;

    if (!API.isAuthenticated()) {
        displayElement.innerHTML = '<div class="cost-error"><i class="fas fa-lock"></i> Please login to view cost trends</div>';
        return;
    }

    displayElement.innerHTML = '<div class="cost-loading"><i class="fas fa-spinner fa-spin"></i> Loading cost trends...</div>';

    try {
        const response = await API.get('/costs/trends');

        if (!response.daily_costs || response.daily_costs.length === 0) {
            displayElement.innerHTML = '<div class="no-costs">No cost trend data available</div>';
            return;
        }

        // Simple text-based chart for now
        let html = '<div class="trends-list">';
        const recentDays = response.daily_costs.slice(-7); // Last 7 days

        recentDays.forEach(day => {
            const date = new Date(day.date).toLocaleDateString();
            html += `
                <div class="trend-item">
                    <div class="trend-date">${date}</div>
                    <div class="trend-cost">$${parseFloat(day.cost || 0).toFixed(2)}</div>
                </div>`;
        });

        html += '</div>';
        html += `<div class="trends-summary">Showing last 7 days of ${response.daily_costs.length} total days</div>`;

        displayElement.innerHTML = html;
    } catch (error) {
        displayElement.innerHTML = `<div class="cost-error">
            <i class="fas fa-exclamation-triangle"></i> Error loading cost trends: ${error.message}
        </div>`;
    }
}

async function loadTagCosts(month = null) {
    const displayElement = document.getElementById('tag-costs-display');
    if (!displayElement) return;

    if (!API.isAuthenticated()) {
        displayElement.innerHTML = '<div class="cost-error"><i class="fas fa-lock"></i> Please login to view tagged costs</div>';
        return;
    }

    displayElement.innerHTML = '<div class="cost-loading"><i class="fas fa-spinner fa-spin"></i> Loading tagged costs...</div>';

    try {
        const url = month ? `/costs/by-tag?month=${month}` : '/costs/by-tag';
        const response = await API.get(url);

        if (!response.services || response.services.length === 0) {
            displayElement.innerHTML = '<div class="no-costs">No "Service" tags found in Cost Explorer yet. Tags can take 24-48 hours to appear in cost reports.</div>';
            return;
        }

        let html = '<div class="service-list">';
        response.services.forEach(service => {
            html += `
                <div class="service-item">
                    <div class="service-name">${service.service}</div>
                    <div class="service-cost">$${parseFloat(service.cost || 0).toFixed(2)}</div>
                </div>`;
        });
        html += '</div>';

        displayElement.innerHTML = html;
    } catch (error) {
        displayElement.innerHTML = `<div class="cost-error">
            <i class="fas fa-exclamation-triangle"></i> Error loading tagged costs: ${error.message}
        </div>`;
    }
}

// Budget Management Functions
async function loadBudgetStatus() {
    const displayElement = document.getElementById('budget-status');
    if (!displayElement) return;

    if (!API.isAuthenticated()) {
        displayElement.innerHTML = '<div class="budget-error"><i class="fas fa-lock"></i> Please login to view budget status</div>';
        return;
    }

    displayElement.innerHTML = '<div class="budget-loading"><i class="fas fa-spinner fa-spin"></i> Loading budget status...</div>';

    try {
        const response = await API.get('/budgets/status');
        console.log('Budget response:', response); // Debug log

        if (!response.budgets || response.budgets.length === 0) {
            displayElement.innerHTML = '<div class="no-budgets">No budget alerts configured. Create your first budget to get started.</div>';
            return;
        }

        displayBudgetStatus(response.budgets);
    } catch (error) {
        console.error('Budget loading error:', error); // Debug log
        displayElement.innerHTML = '<div class="budget-error">No budgets configured. Create your first budget to get started.</div>';
    }
}

function displayBudgetStatus(budgets) {
    const display = document.getElementById('budget-status');
    console.log('Displaying budgets:', budgets); // Debug log

    if (!budgets || budgets.length === 0) {
        display.innerHTML = '<div class="no-budgets">No budgets configured. Create your first budget to get started.</div>';
        return;
    }

    display.innerHTML = `
        <div class="budget-list">
            ${budgets.map(budget => {
                const currentSpending = parseFloat(budget.current_spending || 0);
                const monthlyLimit = parseFloat(budget.monthly_limit || 0);
                const percentage = monthlyLimit > 0 ? Math.round((currentSpending / monthlyLimit) * 100) : 0;
                const projectedCost = budget.projected_monthly ? parseFloat(budget.projected_monthly).toFixed(2) : 'N/A';
                const lastUpdated = budget.last_updated ? new Date(budget.last_updated) : new Date();

                return `
                <div class="budget-item ${getBudgetClass(budget)}">
                    <div class="budget-header">
                        <div class="budget-name">
                            <i class="${getBudgetIcon(budget)}"></i>
                            ${budget.budget_name || budget.name || 'Unnamed Budget'}
                        </div>
                        <div class="budget-percentage">${percentage}%</div>
                    </div>
                    <div class="budget-details">
                        <div class="budget-amounts">
                            <span>$${currentSpending.toFixed(2)} / $${monthlyLimit.toFixed(2)}</span>
                            <span class="projected">Projected: $${projectedCost}</span>
                        </div>
                        <div class="budget-progress">
                            <div class="progress-bar">
                                <div class="progress-fill ${getBudgetClass(budget)}" style="width: ${Math.min(percentage, 100)}%"></div>
                            </div>
                        </div>
                        <div class="budget-meta">
                            <span>Status: ${budget.status || 'on_track'}</span>
                            <span>Last Updated: ${lastUpdated.toLocaleDateString()}</span>
                        </div>
                        <div class="budget-actions">
                            <button class="btn btn-sm btn-secondary" onclick="editBudget('${budget.budget_id || budget.name}')">
                                <i class="fas fa-edit"></i> Edit
                            </button>
                            <button class="btn btn-sm btn-danger" onclick="deleteBudget('${budget.budget_id || budget.name}')">
                                <i class="fas fa-trash"></i> Delete
                            </button>
                        </div>
                    </div>
                </div>
                `;
            }).join('')}
        </div>
    `;
}

function getBudgetClass(budget) {
    const currentSpending = parseFloat(budget.current_spending || 0);
    const monthlyLimit = parseFloat(budget.monthly_limit || 0);
    const percentage = monthlyLimit > 0 ? (currentSpending / monthlyLimit) * 100 : 0;

    if (percentage >= 100) return 'over-budget';
    if (percentage >= 80) return 'warning';
    return 'on-track';
}

function getBudgetIcon(budget) {
    const currentSpending = parseFloat(budget.current_spending || 0);
    const monthlyLimit = parseFloat(budget.monthly_limit || 0);
    const percentage = monthlyLimit > 0 ? (currentSpending / monthlyLimit) * 100 : 0;

    if (percentage >= 100) return 'fas fa-exclamation-triangle';
    if (percentage >= 80) return 'fas fa-exclamation-circle';
    return 'fas fa-check-circle';
}

function showBudgetModal() {
    document.getElementById('budget-modal').style.display = 'block';
    initializeBudgetForm();
    // Pre-fill email with current user's email
    const userEmail = localStorage.getItem('user_email');
    if (userEmail) {
        document.getElementById('notification-email').value = userEmail;
    }
}

function closeBudgetModal() {
    document.getElementById('budget-modal').style.display = 'none';
    document.getElementById('budget-form').reset();

    // Reset form to create mode
    const form = document.getElementById('budget-form');
    form.removeAttribute('data-edit-mode');

    // Reset modal title and button
    document.querySelector('#budget-modal h2').textContent = 'Configure Budget Alert';
    document.querySelector('#budget-form button[type="submit"]').textContent = 'Create Budget Alert';
}

// Initialize budget form when modal is shown
function initializeBudgetForm() {
    const budgetForm = document.getElementById('budget-form');
    if (budgetForm && !budgetForm.hasAttribute('data-initialized')) {
        budgetForm.setAttribute('data-initialized', 'true');
        budgetForm.addEventListener('submit', async function(e) {
            e.preventDefault();

            const budgetData = {
                budget_name: document.getElementById('budget-name').value,
                monthly_limit: parseFloat(document.getElementById('budget-limit').value),
                thresholds: [
                    parseInt(document.getElementById('warn-threshold').value),
                    parseInt(document.getElementById('alert-threshold').value)
                ],
                service_filter: document.getElementById('aws-service').value,
                email: document.getElementById('notification-email').value
            };

            try {
                const editMode = budgetForm.getAttribute('data-edit-mode');

                if (editMode) {
                    // Update existing budget
                    const response = await API.put(`/budgets/update/${encodeURIComponent(editMode)}`, budgetData);
                    if (response) {
                        alert('Budget updated successfully!');
                        closeBudgetModal();
                        loadBudgetStatus();
                    }
                } else {
                    // Create new budget
                    const response = await API.post('/budgets/configure', budgetData);
                    if (response) {
                        alert('Budget alert configured successfully!');
                        closeBudgetModal();
                        loadBudgetStatus();
                    }
                }
            } catch (error) {
                const action = budgetForm.getAttribute('data-edit-mode') ? 'updating' : 'creating';
                alert(`Error ${action} budget: ` + error.message);
            }
        });
    }
}
