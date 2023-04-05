
function update_tx_table(page=1) {

    document.querySelector(".status-table-wrapper").innerHTML = `
        <div class="w-100">
            <div class="mb-3 d-flex  justify-content-center align-items-center flex-wrap">
                <div class="spinner-grow spinner-grow-sm text-primary" role="status"><span class="visually-hidden">Loading...</span></div>&nbsp;
                <div class="spinner-grow spinner-grow-sm text-primary" role="status"><span class="visually-hidden">Loading...</span></div>&nbsp;
                <div class="spinner-grow spinner-grow-sm text-primary" role="status"><span class="visually-hidden">Loading...</span></div>
            </div>
        </div>
    `;

    fetch(`/parts/tron-multiserver`).then(function (response) {
        return response.text();
    }).then(function (html) {
        document.querySelector(".status-table-wrapper").innerHTML = html;
    })
}



function tron_make_active(server_id) {
    fetch(`/parts/tron-multiserver?server_id=${server_id}`, {method: 'POST'}).then(function (response) {
        return response.text();
    }).then(function (html) {
        document.querySelector(".status-table-wrapper").innerHTML = html;
    })
}


window.addEventListener('DOMContentLoaded',function(){
    update_tx_table();
});
