function refreshRates()
{
    let currentRates = document.getElementsByClassName("current-exchange-value");
    let totalMoney = document.getElementsByClassName("total-usd-value");
    let coinAmount = document.getElementsByClassName("coin-amount-value");
    for(let i = 0; i < currentRates.length; i++)
    {
        currentRates[i].id = currentRates[i].id.toLowerCase();
    }
    helperCycleBinanceRates(currentRates,totalMoney,coinAmount);

    function helperCycleBinanceRates(currentRates,totalMoney,coinAmount)
    {
        for(let i = 0; i < currentRates.length; i++)
        {
            getBinanceRealTRates(currentRates[i].id, currentRates[i],totalMoney[i],coinAmount[i]);
            
        }
    }

    function getBinanceRealTRates(pairName, currentRate,totalMoney,coinAmount)
    {
        let url = 'wss://stream.binance.com:9443/ws/' + pairName + '@miniTicker';
        let bSocket = new WebSocket(url);
        bSocket.onmessage = function(data) {
            console.log(data);
            let quotation = JSON.parse(data.data);
            let price = parseFloat(quotation['c']);
            currentRate.innerHTML = price;
            if(coinAmount.innerHTML != "--")
            {
                totalMoney.innerHTML = precise(parseFloat(currentRate.innerHTML) * parseFloat(coinAmount.innerHTML));
            }
        }
    }
    function precise(x)
    {   
        return x.toFixed(2);
    }
}

function refreshWalletInfo()
{  
    let serverStatus = document.getElementsByClassName("server-status");
    let walletStatus = document.getElementsByClassName("wallet-status");
    let coinAmount = document.getElementsByClassName("coin-amount-value");

    helperCycleWalletInfo(serverStatus,walletStatus,coinAmount);
    setInterval(function(){ 
        helperCycleWalletInfo(serverStatus,walletStatus,coinAmount);
    }, 10000);

    function helperCycleWalletInfo(serverStatus,walletStatus,coinAmount)
    {
        for(let i = 0; i < serverStatus.length; i++)
        {
            getWalletInfo(serverStatus[i], walletStatus[i],coinAmount[i]);
        }
    }



    function getWalletInfo(serverStatus,walletStatus,coinAmount)
    {
        let url = "/api/v1/"+coinAmount.id +"/status";
        let http = new XMLHttpRequest();
        http.onload = function(){
            let data = JSON.parse(this.responseText);
            if(data['amount'] !== false)
            {
                coinAmount.innerHTML = data['amount'];
            }
            setWallesStatus(serverStatus,walletStatus,data['server'])
        }
        http.open("GET", url, true);
        http.send();
    }

    function setWallesStatus(serverStatusF,walletStatus,serverStatus)
    {
        let splits = serverStatus.split(" ", 1);
        if(splits[0] == "Synced")
        {
            serverStatusF.innerHTML = serverStatus;
            serverStatusF.style.color = "#198754";
            walletStatus.innerHTML = "Online";
            walletStatus.style.color = "#198754";
        } 
        else if(splits[0] == "Sync")
        {
            serverStatusF.innerHTML = serverStatus;
            serverStatusF.style.color = "#198754";
            walletStatus.innerHTML = "Offline";
            walletStatus.style.color = "#E92b18";
        } 
        else
        {
            serverStatusF.innerHTML = serverStatus;
            serverStatusF.style.color = "#E92b18";
            walletStatus.innerHTML = "Offline";
            walletStatus.style.color = "#E92b18";
        }
    }
}
function setPolicyStatus()
{
    let policyStatus = document.querySelectorAll(".pstatus"); 
    policyStatus.forEach(item => {
        switch(item.innerHTML)
        {
        case "False":
        {
            item.innerHTML = "Disabled";
            item.style.color = "#dc3545";
            break;
        }
        case "True":
        {
            item.innerHTML = "Enabled";
            item.style.color = "#198754"; 
            break;
        }
        }
    });

}
function APIStatus()
{
    const activeStatus = "Enabled";
    const unactiveStatus = "Disabled";
    let APIswitcher = document.querySelector(".apistatus");
    function getStatus()
    {
        const http1 = new XMLHttpRequest()
        http1.open("GET","/api/v1/" + crypto + "/payment-gateway");
        http1.onload = function(){
            let data = checkAnswer(this);
            if(data != false)
            {
                if(data["enabled"])
                {
                    setStatus(activeStatus);
                }
                else
                {
                    setStatus(unactiveStatus);
                }
            }
        }
        http1.send();
    }
    function setStatus(status)
    {
        if(status == activeStatus)
        {
            let status = document.getElementById('API-status');
            APIswitcher.innerText = unactiveStatus;
            status.classList.add('API-status-active');
            status.classList.remove('API-status-inactive');
            status.innerHTML = "Enabled";
        }
        else
        {
            let status = document.getElementById('API-status');
            APIswitcher.innerText = activeStatus;
            status.classList.add('API-status-inactive');
            status.classList.remove('API-status-active');
            status.innerHTML = "Disabled";
        }
    }
    function checkAnswer(response)
    {
        if(response.status == 200)
        {
            let data = JSON.parse(response.responseText);
            if(data['status'] != "success")
            {
                alert(data['message']);
                return false;
            }
            else
            {
                return data;
            }
        }
        alert("Response stauts: " + response.status);
        return false;
    }
    window.addEventListener('DOMContentLoaded',getStatus);
}
APIStatus();
window.addEventListener('DOMContentLoaded',function(){
    refreshRates();
    refreshWalletInfo();
    setPolicyStatus();
});