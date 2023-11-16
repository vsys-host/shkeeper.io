const crypto = document.getElementById('cryptoname').getAttribute("cryptoname");
const BTC = "BTC";
const LTC = "LTC";
const DOGE = "DOGE"
console.log(crypto);

function dropdown()
{
  function addEventsToDropdown()
  {
    let dropdownBtn = document.querySelectorAll('.dropdown__button');
    let dropdownItems = document.querySelectorAll('.dropdown__text');
    let dropdownCurrent = document.querySelectorAll('.dropdown__current');
    dropdownCurrent.forEach( item=>{
        item.addEventListener('click',function(){
            document.querySelectorAll('.dropdown__body')[0].classList.add("dropdown-show");
        });
    });

    dropdownBtn.forEach( item=>{
        item.addEventListener('click',toggleDropdown);
    });

    dropdownItems.forEach( item=>{ item.addEventListener('click',chooseItem);});

  }
  function autocomplete()
  {
    let addressField = document.getElementById("paddress");
    if (!addressField) return;

    function filterAddItems()
    {
        let dropdownItems = document.querySelectorAll('.dropdown__item');
        dropdownItems.forEach(item => {
            let itemValue = item.querySelector('.dropdown__text').innerText;
            let re = new RegExp(addressField.value);
            console.log(re.test(itemValue));
            if(!re.test(itemValue) && addressField.value != "")
            {
                item.classList.add("dropdown__item-hide");
            }
            else{
                item.classList.remove("dropdown__item-hide");
            }
        });
    }
    filterAddItems()
    addressField.addEventListener('keyup',function(){filterAddItems()});
  }

  function toggleDropdown()
  {
    let dropdownBody=document.querySelectorAll('.dropdown__body');
    dropdownBody.forEach(item => {item.classList.toggle('dropdown-show');});
  }
  function chooseItem()
  {
    let value = this.innerText;
    let paddress = document.getElementById("paddress");
    paddress.value = value;
    toggleDropdown();
  }
  addEventsToDropdown();
  autocomplete();
  window.onclick = function(event){
    if(event.target.localName != ("svg" || "use")){
        if(!event.target.className.match('dropdown'))
        {
        let dropdowns = document.querySelectorAll('.dropdown__body');
        dropdowns.forEach( item=>{
            item.classList.remove("dropdown-show");
        });
        }
    }
  }
}

let deleteAdd = function(){

  let deleteButtons = document.querySelectorAll('.delete-button');

  deleteButtons.forEach(item => {
    item.addEventListener('click', deleteAddress);
  });

  function deleteAddress()
  {
    let destinationNode = this.parentElement;
    let destinationAdd = destinationNode.firstElementChild.innerText;
    let jsonObj = JSON.stringify({
      action: "delete",
      daddress: destinationAdd
    });

    destinationNode.remove();

    const httpAPI = new XMLHttpRequest();

    httpAPI.onload = function(){
      destinationNode.remove();
    }
    httpAPI.open("POST","/api/v1/" + crypto + "/payout_destinations",true);
    httpAPI.send(jsonObj);
  }
}

function policyFunc(){
  let policyOption = document.getElementById("ppolicy");
  if (!policyOption) return;
  policyOption.addEventListener("click",policyChange);
  let policyStatus = document.getElementById("pstatus");
  policyStatus.addEventListener("click",policyStatusChange);

  window.addEventListener('DOMContentLoaded',function(){
    policyChange();
    setPolicyStatus();
  });

  function policyChange()
  {
    let policyOption = document.getElementById("ppolicy");
    if (!policyOption) return;
    let policyString = policyOption.parentElement;
    //let status = document.querySelector(".success-text");
    switch(policyOption.value){
      case "manual":
        policyString.children[1].classList.add("policy-element-hide");
        policyString.children[2].classList.add("policy-element-hide");
        policyString.children[3].classList.add("policy-element-hide");
        //status.style.color = "var(--danger-color)";
        //status.innerText = "Off";
        break;
      case "scheduled":
        policyString.children[1].classList.remove("policy-element-hide");
        policyString.children[2].classList.remove("policy-element-hide");
        policyString.children[3].classList.add("policy-element-hide");
        //status.style.color = "var(--success-color)";
        //status.innerText = "On";
        setSheduledParam();
        break;
      case "limit":
        policyString.children[1].classList.remove("policy-element-hide");
        policyString.children[2].classList.add("policy-element-hide");
        policyString.children[3].classList.remove("policy-element-hide");
        //status.style.color = "var(--success-color)";
        //status.innerText = "On";
        break;
    }
  }
  function setSheduledParam()
  {
    const hour = 60;
    const day = 1440;
    let input = document.getElementById("poschedulud-val");
    let select = document.getElementById("poschedulud-term");
    let days = Math.floor(parseInt(input.value) / day);
    let hours = Math.floor(parseInt(input.value) / hour);
    if(days)
    {
        select.selectedIndex = 2;
        input.value = days;
    }
    else if(hours)
    {
        select.selectedIndex = 1;
        input.value = hours;
    }
  }
  function policyStatusChange()
  {
    let policyStatus = this;
    switch(policyStatus.innerHTML)
    {
      case "On":
      {
        policyStatus.innerHTML = "Off";
        policyStatus.style.color = "var(--danger-color)";
        break;
      }
      case "Off":
      {
        policyStatus.innerHTML = "On";
        policyStatus.style.color = "var(--success-color)";
        break;
      }
    }
  }
  function setPolicyStatus()
  {
    let policyStatus = document.getElementById("pstatus");
    switch(policyStatus.innerHTML)
    {
      case "False":
      {
        policyStatus.innerHTML = "Off";
        policyStatus.style.color = "var(--danger-color)";
        break;
      }
      case "True":
      {
        policyStatus.innerHTML = "On";
        policyStatus.style.color = "var(--success-color)";
        break;
      }
    }
  }
}

function sendAction()
{

  let sendButton = document.getElementById("sbutton");

  sendButton.addEventListener("click",function(){
      sendData();

  });

  function sendData()
  {
    let data = composeData();
    let http = new XMLHttpRequest();
    http.onload = function(){
      console.log("Ok!");
      alert("Saved");
      addAdd();
    }
    http.open("POST","/api/v1/" + crypto + "/autopayout",true);
    if(data != false)
    {
      http.send(data);
    }
    else
    {
      alert("Please, Fields cannot be empty or check if the values are entered correctly.")
    }
  }
  function addAdd()
  {
    let data = composeAddData();
    let http = new XMLHttpRequest();
    http.onload = function(){
      console.log("Ok!");
      refreshAddList();
    }
    http.open("POST","/api/v1/" + crypto + "/payout_destinations",true);
    if(data != false)
    {
      http.send(data);
    }
    else
    {
      alert("Please, Fields cannot be empty or check if the values are entered correctly.")
    }
  }

  function composeAddData()
  {
    let check = true;
    let payoutAdd = document.getElementById("paddress").value;
    if(check == false)
    {
      return false;
    }

    return JSON.stringify({
        action: "add",
        daddress: payoutAdd,
        comment: "",

    });
  }


  function composeData()
  {
    let check = true;
    let payoutAdd = validateAddressValue(document.getElementById("paddress"));
    let payoutFee = document.getElementById("pfee").value.trim();
    let policyStatus = document.getElementById('pstatus');
    switch(policyStatus.innerHTML)
    {
      case "On":
        policyStatus = true;
        break;
      case "Off":
        policyStatus = false;
        break
    }
    let policyOption = document.getElementById("ppolicy").value;
    let policyValue;
    switch(policyOption)
    {
      case "manual":
        policyValue = "none";
        break;
      case "scheduled":
        policyValue = getSheduled();
        break;
      case "limit":
        policyValue = validateFloatValue(document.getElementById("polimit-val"));
        break;
    }
    let paymentPartiallyPaid = validateFloatValue(document.getElementById("llimit"));
    let paymentAddedFee = validateFloatValue(document.getElementById("ulimit"));
    let recalculateTerm = getRecalcTermHour();
    let confirationNumber = validateNumValue(document.getElementById("confirmations"));
    if(check == false)
    {
      return false;
    }

    return JSON.stringify({
      add: payoutAdd,
      fee: payoutFee,
      policy: policyOption,
      policyStatus: policyStatus,
      policyValue: policyValue,
      partiallPaid:  paymentPartiallyPaid,
      addedFee: paymentAddedFee,
      confirationNum: confirationNumber,
      recalc: recalculateTerm //int
    });
    function validateNumValue(element)
    {
      element.value = element.value.trim();
      if(element.value.match(/^\d+$/))
      {
        element.classList.remove("red-highlight");
      }
      else{
        element.classList.add("red-highlight");
        check = false;
      }
      return element.value;
    }
    function validateFloatValue(element)
    {
      element.value = element.value.trim();
      if(element.value.match(/^\d+\.*\d*$/))
      {
        element.classList.remove("red-highlight");
      }
      else{
        element.classList.add("red-highlight");
        check = false;
      }
      return element.value;
    }
    function validateAddressValue(element)
    {
      element.value = element.value.trim();
      if(element.value != "" && element.value != "None")
      {
        if(crypto == BTC)
        {
          let BTCRegExp = new RegExp('^(?:[13]{1}[a-km-zA-HJ-NP-Z1-9]{26,33}|bc1[a-z0-9]{39,59}|tb1[a-z0-9]{39,59})$');
          if(BTCRegExp.test(element.value))
          {
            document.querySelector(".dropdown__header").classList.remove("red-highlight");
          }
          else
          {
            alert("Destination Address doesn't match Valid Bitcoin address.");
            document.querySelector(".dropdown__header").classList.add("red-highlight");
            check = false;
          }
        }
        else if(crypto == LTC)
        {
          let BTCRegExp = new RegExp('^([LM3][a-km-zA-HJ-NP-Z1-9]{26,33}|ltc1[a-z0-9]{39,59})$');
          if(BTCRegExp.test(element.value))
          {
            document.querySelector(".dropdown__header").classList.remove("red-highlight");
          }
          else
          {
            alert("Destination Address doesn't match Valid Litecoin address.");
            document.querySelector(".dropdown__header").classList.add("red-highlight");
            check = false;
          }
        }
        else if(crypto == DOGE)
        {
          let BTCRegExp = new RegExp('^D{1}[5-9A-HJ-NP-U]{1}[1-9A-HJ-NP-Za-km-z]{32}$');
          if(BTCRegExp.test(element.value))
          {
            document.querySelector(".dropdown__header").classList.remove("red-highlight");
          }
          else
          {
            alert("Destination Address doesn't match Valid Dogecoin address.");
            document.querySelector(".dropdown__header").classList.add("red-highlight");
            check = false;
          }
        }

      }
      // else{
      //   document.querySelector(".dropdown__header").classList.add("red-highlight");
      //   check = false;
      // }
      return element.value;
    }

    function getRecalcTermHour()
    {
        let value = validateNumValue(document.getElementById('recalculate-val'));
        let term = document.getElementById('recalculate-term').value;
        return parseInt(value)*term;

    }
    function getSheduled()
    {
        let value = validateNumValue(document.getElementById("poschedulud-val"));
        let term = document.getElementById("poschedulud-term").value;
        return value*term;

    }


  }
}

function serverStatus()
{


    function getServerInfo()
    {
        let url = "/api/v1/"+crypto +"/status";
        let http = new XMLHttpRequest();
        http.onload = function(){
            let data = JSON.parse(this.responseText);
            setServerStatus(data['server'])
        }
        http.open("GET", url, true);
        http.send();
    }

    function setServerStatus(serverStatus)
    {
        let serverStatusEl = document.getElementById("server-status");
        let splits = serverStatus.split(" ", 1);
        if (serverStatusEl) {
          if(splits[0] == "Synced")
          {
              serverStatusEl.innerHTML = "Server Online";
              serverStatusEl.style.color = "var(--success-color)";
          }
          else if(splits[0] == "Sync")
          {
              serverStatusEl.innerHTML = "Server Syncing";
              serverStatusEl.style.color = "var(--success-color)";
          }
          else
          {
              serverStatusEl.innerHTML = "Server Offline";
              serverStatusEl.style.color = "var(--danger-color)";
          }
        }
    }
    getServerInfo();
    setInterval(function(){
        getServerInfo();
    }, 5000);
}

function refreshAddList()
{
    function getAddListSS()
    {
        let requestBody = JSON.stringify(
            {
              action: "list"
            }
        );
        let listHttp = new XMLHttpRequest();
        listHttp.open('POST',"/api/v1/" + crypto + "/payout_destinations",true);
        listHttp.send(requestBody);
        listHttp.onload = function()
        {
            let data = checkAnswer(this.responseText);
            if(data == false)
            {
                console.log("Error, or empty list!");
            }
            else{
                clearDropdownBody();
                data['payout_destinations'].forEach(item=>{
                    addHTMLElement(item['addr']);
                });
            }


        };


    }
    function chooseItem()
    {
        let value = this.innerText;
        let paddress = document.getElementById("paddress");
        paddress.value = value;
        toggleDropdown();
    }
    function checkAnswer(responseText)
    {
        let data = JSON.parse(responseText);
        if(data['status'] != "success")
        {
            return false;
        }
        else
        {
            return data;
        }
    }
    function createEmpEnt(addr,comment)
    {
      let itemSample = document.querySelector('.dropdown__item-sample');
      let newEnt = itemSample.cloneNode(true);
      newEnt.classList.remove("dropdown__item-sample");
      newEnt.classList.add("dropdown__item");
      let textField = newEnt.querySelector('.dropdown__text');
      textField.innerHTML = addr;
      return newEnt;
    }
    function addHTMLElement(addr,comment)
    {
      let itemSample = createEmpEnt(addr,comment);
      let managerNode = document.querySelector('.dropdown__body');
      managerNode.appendChild(itemSample);
      itemSample.addEventListener('click',chooseItem);
    }
    function clearDropdownBody()
    {
        let itemList = document.getElementsByClassName('dropdown__item');
        while(itemList.length > 0){
            itemList[0].parentNode.removeChild(itemList[0]);
        }
    }
    getAddListSS();
}
function paymentGatwey()
{
    function APIStatus()
    {
        const activeStatus = "Activate";
        const unactiveStatus = "Deactivate";
        let APIswitcher = document.getElementById("API-switcher");
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
              status.innerHTML = "Active";
            }
            else
            {
              let status = document.getElementById('API-status');
              APIswitcher.innerText = activeStatus;
              status.classList.add('API-status-inactive');
              status.classList.remove('API-status-active');
              status.innerHTML = "Inactive";
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
        function sendAPIStatus(status, statusDescr)
        {
            const http2 = new XMLHttpRequest();
            http2.open("POST","/api/v1/" + crypto + "/payment-gateway ", true);
            http2.onload = function(){
                let data = checkAnswer(this);
                if(data != false)
                {
                    APIswitcher.innerText = statusDescr;
                    setStatus(statusDescr);
                }
            }
            http2.send(JSON.stringify({"enabled": status}));
        }
        function switchAPIStatus()
        {
            if(APIswitcher.innerText == activeStatus)
            {
                sendAPIStatus(true,activeStatus);
            }
            else if(APIswitcher.innerText == unactiveStatus)
            {
                sendAPIStatus(false,unactiveStatus);
            }
        }

        window.addEventListener('DOMContentLoaded',getStatus);
        document.getElementById("API-switcher").addEventListener('click',switchAPIStatus);
    }
    function APIToken()
    {
      const tokenLength = 16;
      let tokenHTML = document.getElementById("API-token");
      let generateBtn = document.getElementById("generateAPIBtn");
      function generateAPIToken(length)
      {
        var result           = '';
        var characters       = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_';
        var charactersLength = characters.length;
        for ( var i = 0; i < length; i++ ) {
          result += characters.charAt(Math.floor(Math.random() * charactersLength));
        }
        return result;
      }
      function sendAPIToken()
      {
        let token = generateAPIToken(tokenLength);
        const httpToken = new XMLHttpRequest();
        httpToken.open("POST","/api/v1/" + crypto + "/payment-gateway/token");
        httpToken.send(JSON.stringify({"token":token}));
        httpToken.onload = function()
        {
          if(checkAnswer(this))
          {
            tokenHTML.innerHTML = token;
            console.log("Token generated.");
          }
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
      generateBtn.addEventListener("click",sendAPIToken);
    }
    APIToken();
    APIStatus();
}

paymentGatwey();
serverStatus();
deleteAdd();
policyFunc();
sendAction();
dropdown();
