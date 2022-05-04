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



window.addEventListener('DOMContentLoaded',function(){
    refreshRates();
    refreshWalletInfo();
});