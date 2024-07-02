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
        if (['usdtusdt', 'eth-usdtusdt', 'bnb-usdtusdt', 'polygon-usdtusdt', 'avalanche-usdtusdt'].includes(pairName)) {
            currentRate.innerHTML = "1";
            setInterval(() => {
                if (coinAmount.innerHTML != "--") {
                    totalMoney.innerHTML = precise(parseFloat(currentRate.innerHTML) * parseFloat(coinAmount.innerHTML));
                }
            }, 1000);
            return;
        }

        if (['eth-usdcusdt', 'bnb-usdcusdt', 'polygon-usdcusdt', 'avalanche-usdcusdt'].includes(pairName)) {
            pairName = 'usdcusdt';
        }

        let url = 'wss://stream.binance.com:9443/ws/' + pairName + '@miniTicker';
        let bSocket = new WebSocket(url);
        bSocket.onmessage = function(data) {
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
            serverStatusF.style.color = "var(--success-color)";
            walletStatus.innerHTML = "Online";
            walletStatus.style.color = "var(--success-color)";
        }
        else if(splits[0] == "Sync")
        {
            serverStatusF.innerHTML = serverStatus;
            serverStatusF.style.color = "var(--success-color)";
            walletStatus.innerHTML = "Offline";
            walletStatus.style.color = "var(--danger-color)";
        }
        else
        {
            serverStatusF.innerHTML = serverStatus;
            serverStatusF.style.color = "var(--danger-color)";
            walletStatus.innerHTML = "Offline";
            walletStatus.style.color = "var(--danger-color)";
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
            item.style.color = "var(--danger-color)";
            break;
        }
        case "True":
        {
            item.innerHTML = "Enabled";
            item.style.color = "var(--success-color)";
            break;
        }
        }
    });

}
function APIStatus()
{
    const activeStatus = "Enabled";
    const unactiveStatus = "Disabled";
    const offlineStatus = "Offline"
    let APIswitchers = document.querySelectorAll(".apistatus");
    for(let i = 0;i<APIswitchers.length;i++)
    {
        let APIswitcher = APIswitchers[i];
        let crypto = APIswitcher.getAttribute('crypto');
        getStatus();
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
                else{
                setStatus(offlineStatus);
                }
            }
            http1.send();
        }
        function setStatus(status)
        {
            if(status == activeStatus)
            {
                APIswitcher.innerText = activeStatus;
                APIswitcher.style.color="var(--success-color)";
            }
            else if(status == unactiveStatus)
            {
                APIswitcher.innerText = unactiveStatus;
                APIswitcher.style.color="var(--danger-color)";
            }
            else
            {
                APIswitcher.innerText = offlineStatus;
                APIswitcher.style.color="var(--danger-color)";
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
            return false;
        }
    }
}
window.addEventListener('DOMContentLoaded',function(){
    APIStatus();
    refreshRates();
    refreshWalletInfo();
    setPolicyStatus();
});
